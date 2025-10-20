import os
from ebooklib import epub, ITEM_COVER, ITEM_DOCUMENT
from bs4 import BeautifulSoup


def _update_toc_recursive(toc_list, title_map):
    for item in toc_list:
        if (
            isinstance(item, (list, tuple))
            and len(item) == 2
            and isinstance(item[0], str)
        ):
            _update_toc_recursive(item[1], title_map)
        elif hasattr(item, "href") and item.href in title_map:
            item.title = title_map[item.href]


def extract_content_from_chapters(chapter_items, logger, verbose=True):
    if verbose:
        logger("Extracting content and adding unique chapter identifiers...")
    full_content_for_api = ""
    extraction_data = []

    for item in chapter_items:
        chapter_id = item.get_name()
        id_tag = f"[CHAPTER_ID::{chapter_id}]"

        soup = BeautifulSoup(item.get_content(), "html.parser")
        body = soup.find("body")
        if not body:
            continue

        image_tags_for_chapter = []
        for i, img in enumerate(body.find_all("img")):
            placeholder = f"\n[IMAGE_PLACEHOLDER_{i}]\n"
            image_tags_for_chapter.append(str(img))
            img.replace_with(placeholder)

        chapter_text = body.get_text(separator="\n", strip=True)
        full_content_for_api += f"{id_tag}\n{chapter_text}\n---\n"
        extraction_data.append((chapter_id, image_tags_for_chapter))

    if verbose:
        logger("Content extracted successfully.", level="SUCCESS")
    return full_content_for_api, extraction_data


def create_translated_epub(
    original_path, translation_map, chapters_to_replace, extraction_data, logger
):
    logger("Reconstructing EPUB with translated content...")
    dir_name, file_name = os.path.split(original_path)
    new_file_path = os.path.join(
        dir_name, os.path.splitext(file_name)[0] + "_translated.epub"
    )

    book = epub.read_epub(original_path)

    style_item = book.get_item_with_id("style_default")
    if not style_item:
        logger("Stylesheet not found, creating a new one.")
        stylesheet_content = """
        body { font-family: serif; line-height: 1.6; margin: 5px; }
        h1 { text-align: center; font-weight: bold; page-break-before: always; margin-top: 2em; margin-bottom: 2em; }
        p { text-align: justify; text-indent: 1.5em; margin-top: 0; margin-bottom: 0; }
        img { max-width: 100%; height: auto; display: block; margin-left: auto; margin-right: auto; padding-top: 1em; padding-bottom: 1em; }
        """
        style_item = epub.EpubItem(
            uid="style_default",
            file_name="style/default.css",
            media_type="text/css",
            content=stylesheet_content,
        )
        book.add_item(style_item)

    image_map = {href: images for href, images in extraction_data}
    chapters_to_replace_hrefs = {item.get_name() for item in chapters_to_replace}
    newly_translated_titles = {}

    for item in book.get_items_of_type(ITEM_DOCUMENT):
        original_href = item.get_name()

        if (
            original_href in chapters_to_replace_hrefs
            and original_href in translation_map
        ):
            translated_content = translation_map[original_href]
            image_tags = image_map.get(original_href, [])
            lines = translated_content.strip().split("\n")

            title_text, body_content, start_index = item.title, "", 0

            if lines and lines[0].startswith("**") and lines[0].endswith("**"):
                title_text = lines[0].strip("* ").strip()
                start_index = 1
                body_content += f"<h1>{title_text}</h1>\n"

            item.title = title_text
            newly_translated_titles[original_href] = title_text

            for line in lines[start_index:]:
                clean_line = line.strip()
                if not clean_line:
                    continue
                if clean_line.startswith("[IMAGE_PLACEHOLDER_") and clean_line.endswith(
                    "]"
                ):
                    try:
                        img_index = int(clean_line.split("_")[-1].strip("]"))
                        if img_index < len(image_tags):
                            body_content += f"{image_tags[img_index]}\n"
                    except (ValueError, IndexError):
                        body_content += f"<p>{clean_line}</p>\n"
                else:
                    body_content += f"<p>{clean_line}</p>\n"

            if not body_content.strip():
                logger(
                    f"Translated content for '{original_href}' is empty. Skipping modification.",
                    level="WARNING",
                )
                continue

            chapter_dir = os.path.dirname(item.get_name())
            style_path_relative = os.path.relpath(
                style_item.get_name(), chapter_dir
            ).replace("\\", "/")

            html = f"""<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{item.title}</title>
    <link rel="stylesheet" type="text/css" href="{style_path_relative}" />
</head>
<body>{body_content}</body>
</html>"""
            item.set_content(html.encode("utf-8"))
            item.add_item(style_item)

    if newly_translated_titles:
        logger("Updating Table of Contents with new titles...")
        _update_toc_recursive(book.toc, newly_translated_titles)

    logger("Regenerating Table of Contents and Navigation files...")
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    try:
        epub.write_epub(new_file_path, book, {})
        logger(f"Translated e-book saved as: {new_file_path}", level="SUCCESS")
    except Exception as e:
        logger(f"Could not write translated EPUB file: {e}", level="ERROR")


def create_cover_page_from_metadata(epub_path, logger):
    try:
        logger("Starting cover page creation process...")
        book = epub.read_epub(epub_path)
        cover_image_item = None

        logger("Step 1: Checking for dedicated ITEM_COVER type...")
        cover_items = list(book.get_items_of_type(ITEM_COVER))
        if cover_items:
            cover_image_item = cover_items[0]
            logger(
                f"Found cover via ITEM_COVER type: {cover_image_item.get_name()}",
                level="SUCCESS",
            )

        if not cover_image_item:
            logger("Step 2: Checking for 'cover' in metadata...")
            cover_id_meta = book.get_metadata("OPF", "cover")
            if cover_id_meta:
                content_id = cover_id_meta[0][1].get("content")
                if content_id:
                    cover_image_item = book.get_item_with_id(content_id)
                    if cover_image_item:
                        logger(
                            f"Found cover via metadata ID: {cover_image_item.get_name()}",
                            level="SUCCESS",
                        )

        if not cover_image_item:
            logger(
                "No official cover found in metadata or item types. Aborting.",
                level="ERROR",
            )
            return

        logger("Creating and adding a new stylesheet for the cover...")
        stylesheet_content = """
.cover-page {
    text-align: center; margin: 0; padding: 0; height: 100vh;
    display: flex; justify-content: center; align-items: center;
}
.cover-page img {
    max-width: 100%; max-height: 100%; object-fit: contain;
}
"""
        stylesheet = epub.EpubItem(
            uid="style_cover",
            file_name="style/cover.css",
            media_type="text/css",
            content=stylesheet_content.encode("utf-8"),
        )
        book.add_item(stylesheet)

        logger("Creating new cover.xhtml page...")

        cover_page_dir = os.path.dirname("cover.xhtml")
        css_path = os.path.relpath(stylesheet.get_name(), cover_page_dir).replace(
            "\\", "/"
        )
        image_path = os.path.relpath(
            cover_image_item.get_name(), cover_page_dir
        ).replace("\\", "/")

        cover_page = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang="en")
        cover_page.content = f"""<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Cover</title>
    <link rel="stylesheet" type="text/css" href="{css_path}" />
</head>
<body>
    <div class="cover-page">
        <img src="{image_path}" alt="Cover Image" />
    </div>
</body>
</html>""".encode(
            "utf-8"
        )

        book.add_item(cover_page)
        cover_page.add_item(stylesheet)

        logger(
            "Replacing original first page with the new cover page in the book's reading order."
        )
        if book.spine:
            del book.spine[0]
            book.spine.insert(0, cover_page)
        else:
            book.spine.append(cover_page)

        dir_name, file_name = os.path.split(epub_path)
        new_file_name = os.path.splitext(file_name)[0] + "_cover.epub"
        new_file_path = os.path.join(dir_name, new_file_name)

        epub.write_epub(new_file_path, book, {})
        logger(
            f"Successfully created new EPUB with formatted cover page: {new_file_path}",
            level="SUCCESS",
        )

    except Exception as e:
        logger(f"An error occurred during cover creation: {e}", level="ERROR")
