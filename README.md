# MtgPng2Pdf
PDF Generator for PNG image sof Magic cards

## Summary
[MtgPng2Pdf](https://github.com/matthewddunlap/MtgPng2Pdf) takes a deck list and path to diirectory of card images in PNG format downloaded with [ccDownloader](https://github.com/matthewddunlap/ccDownloader) and generates a PDF file for manual (default) or automated cutting (`--cameo`).

By default [MtgPng2Pdf](https://github.com/matthewddunlap/MtgPng2Pdf) will use a random selection of land art if available.

## Requirements
On Debian 12 install requried package
```
sudo apt install chromium chromium-driver jq python3-lxml python3-natsort python3-pil python3-reportlab python3-requests python3-selenium
```

## Usage
```
MtgPng2Pdf.py [-h] [--png-dir PNG_DIR] [--deck-list DECK_LIST]
              [--output-file OUTPUT_FILE] [--output-format {pdf,png}]
              [--png-out-dir PNG_OUT_DIR]
              [--image-server-base-url IMAGE_SERVER_BASE_URL]
              [--image-server-path-prefix IMAGE_SERVER_PATH_PREFIX]
              [--image-server-png-dir IMAGE_SERVER_PNG_DIR]
              [--upload-to-server]
              [--image-server-pdf-dir IMAGE_SERVER_PDF_DIR]
              [--overwrite-server-file] [--debug] [--skip-basic-land]
              [--sort] [--cameo] [--basic-land-set BASIC_LAND_SET]
              [--basic-land-set-mode {prefer,force}]
              [--spell-set SPELL_SET] [--spell-set-mode {prefer,force}]
              [--paper-type {letter,legal}] [--page-margin PAGE_MARGIN]
              [--image-spacing-pixels IMAGE_SPACING_PIXELS]
              [--dpi {72,96,150,300,600}]
              [--page-bg-color PAGE_BG_COLOR]
              [--image-cell-bg-color IMAGE_CELL_BG_COLOR]
              [--cameo-label-font-size CAMEO_LABEL_FONT_SIZE]
              [--cut-lines] [--cut-line-length CUT_LINE_LENGTH]
              [--cut-line-color CUT_LINE_COLOR]
              [--cut-line-width-pt CUT_LINE_WIDTH_PT]
              [--cut-line-width-px CUT_LINE_WIDTH_PX]

Lay out PNG images or copy them based on a deck list.

## Options
```
  -h, --help            show this help message and exit

Primary Operation Modes (choose one output type):
  --png-dir PNG_DIR     Directory containing source PNG files. (default: None)
  --deck-list DECK_LIST
                        Path to deck list. Supports 'COUNT NAME', 'COUNT NAME
                        (SET)', and 'COUNT NAME (SET) NUM' formats. (default:
                        None)
  --output-file OUTPUT_FILE
                        Base name for local PDF/PNG grid output, or just the
                        filename for server upload. Extension auto-added.
                        Defaults to MtgProxyOutput, or <deck_list_name> if
                        --deck-list is used. (default: None)
  --output-format {pdf,png}
                        Format for grid layout output (pdf or png). Ignored if
                        --png-out-dir is used. (default: pdf)
  --png-out-dir PNG_OUT_DIR
                        Output directory for copying PNGs from deck list. If
                        set, grid generation is skipped. (default: None)

Image Server Options:
  --image-server-base-url IMAGE_SERVER_BASE_URL
                        Base URL of the image server. If provided, images will
                        be fetched from this server instead of --png-dir. If
                        --upload-to-server is used, output files will be PUT
                        to this server instead of being saved locally.
                        Required if --upload-to-server is set. (default: None)
  --image-server-path-prefix IMAGE_SERVER_PATH_PREFIX
                        Base path for the art URL. Used for both PNG card
                        image retrieval and, if --upload-to-server is used,
                        constructing the output file path for the PDF.
                        (default: /local_art)
  --image-server-png-dir IMAGE_SERVER_PNG_DIR
                        Relative path (from --image-server-path-prefix) to the
                        directory containing the source PNG files. (default:
                        /)

Image Server Upload Options:
  --upload-to-server    Upload the generated PDF to the image server instead
                        of saving it locally. Requires --image-server-base-
                        url. (default: False)
  --image-server-pdf-dir IMAGE_SERVER_PDF_DIR
                        Subdirectory on the server (relative to --image-
                        server-path-prefix) to upload the final PDF to.
                        (default: /)
  --overwrite-server-file
                        If a file with the same name exists on the server,
                        overwrite it. Default is to fail. (default: False)

General Options:
  --debug               Enable detailed debug messages. (default: False)
  --skip-basic-land     Skip basic lands. (default: False)
  --sort                Sort PNGs alphabetically (for directory scan mode or
                        if --png-out-dir copies all from dir). (default:
                        False)
  --cameo               Use PIL-based PDF generation (modeled after
                        create_pdf.py/utilities.py) when --output-format is
                        pdf. This mode uses fixed layouts from an internal
                        'layouts.json' equivalent and ignores most
                        page/layout/cut-line options. Currently best supports
                        --paper-type letter or a4 (if in layouts). EXPECTS an
                        'assets' FOLDER with registration mark images (e.g.,
                        'letter_registration.jpg') next to the script for
                        proper Cameo output. (default: False)
  --basic-land-set BASIC_LAND_SET
                        Comma-separated list of set codes to filter basic
                        lands by (e.g., 'lea,unh,neo'). Behavior is controlled
                        by --basic-land-set-mode. (default: None)
  --basic-land-set-mode {prefer,force}
                        Controls how --basic-land-set is applied. 'prefer'
                        will use the specified sets if available, but fall
                        back to any set if not. 'force' will fail if no cards
                        from the specified sets are found. (default: prefer)
  --spell-set SPELL_SET
                        Comma-separated list of set codes to filter non-land
                        cards ('spells') by. Behavior is controlled by
                        --spell-set-mode. (default: None)
  --spell-set-mode {prefer,force}
                        Controls how --spell-set is applied. 'prefer' will use
                        the specified sets if available, but fall back to any
                        set if not. 'force' will fail if no cards from the
                        specified sets are found. (default: prefer)

Page and Layout Options (for PDF/PNG grid output; largely IGNORED by --cameo mode):
  --paper-type {letter,legal}
                        Conceptual paper type. For ReportLab PDF: Letter 3x3,
                        Legal 3x4. For --cameo PDF: must match a layout like
                        'letter'. (default: letter)
  --page-margin PAGE_MARGIN
                        Margin around the grid (e.g., '5mm', '0.25in',
                        '10px'). (default: 5mm)
  --image-spacing-pixels IMAGE_SPACING_PIXELS
                        Spacing between images in pixels. (default: 0)
  --dpi {72,96,150,300,600}
                        DPI for output and interpreting inch/mm dimensions.
                        (default: 300)
  --page-bg-color PAGE_BG_COLOR
                        Overall page/canvas background color. (default: white)
  --image-cell-bg-color IMAGE_CELL_BG_COLOR
                        Background color directly behind transparent image
                        parts. (default: black)
  --cameo-label-font-size CAMEO_LABEL_FONT_SIZE
                        [Cameo Mode Only] Font size for the page label. This
                        is a base size in points, which is then scaled by DPI.
                        A reasonable range is 24-48. Must be between 8 and 96.
                        (default: 32)

Cut Line Options (for PDF/PNG grid output; IGNORED by --cameo mode):
  --cut-lines           Enable drawing of cut lines. (default: False)
  --cut-line-length CUT_LINE_LENGTH
                        Length of cut lines (e.g., '3mm', '0.1in', '5px').
                        (default: 3mm)
  --cut-line-color CUT_LINE_COLOR
                        Color of cut lines. (default: gray)
  --cut-line-width-pt CUT_LINE_WIDTH_PT
                        Thickness of cut lines in points (for PDF output).
                        (default: 0.25)
  --cut-line-width-px CUT_LINE_WIDTH_PX
                        Thickness of cut lines in pixels (for PNG output).
                        (default: 1)
```

## Examples
### Generate PDF for manual cutting
```
python3 MtgPng2Pdf.py --png-dir card_images/m15ub --output-format pdf --output-file myDeck.pdf --deck-list myDeck.txt --cut-lines --cut-line-width-pt 2
```

### Generate PDF for automated cutting with Silhouette Cameo (default 300dpi)
```
python3 MtgPng2Pdf.py --png-dir card_images/m15ub --output-format pdf --output-file myDeck.pdf --deck-list myDeck.txt --cameo
```

### Same as above but at 600dpi and skipping basic lands
```
python3 MtgPng2Pdf.py --png-dir card_images/m15ub --output-format pdf --output-file myDeck.pdf --deck-list myDeck.txt --skip-basic-land  --cameo --dpi 600
```

### Use webserver instead of local filesystem
The combination of `--image-server-base-url`, `--image-server-path-prefix`, `--image-server-png-dir` and `--image-server-pdf-dir` transaltes to card images avaialbe at http://mtgproxy:4242/local_art/card_images/7th and output PDF to be uploaded to http://mtgproxy:4242/local_art/decks
```
python3 MtgPng2Pdf.py --image-server-base-url http://mtgproxy:4242 --image-server-path-prefix /local_art --image-server-png-dir card_images/7th --deck-list myDeck.txt --cameo --cameo-label-font-size 48 --upload-to-server --image-server-pdf-dir decks --overwrite-server-file
```

### Same as above but prefer art from Homelands
```
python3 MtgPng2Pdf.py --image-server-base-url http://mtgproxy:4242 --image-server-path-prefix /local_art --image-server-png-dir card_images/7th --deck-list myDeck.txt --cameo --cameo-label-font-size 48 --spell-set hml --upload-to-server --image-server-pdf-dir decks --overwrite-server-file
```
