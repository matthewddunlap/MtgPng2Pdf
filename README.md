# MtgPng2Pdf
PDF Generator for PNG images of Magic cards

## Summary
[MtgPng2Pdf](https://github.com/matthewddunlap/MtgPng2Pdf) takes a deck list and a path to a directory of card images in PNG format, and generates a PDF file for manual (default) or automated cutting (`--cameo`).

By default, [MtgPng2Pdf](https://github.com/matthewddunlap/MtgPng2Pdf) will use a random selection of available art for each card. For more control over card art selection, see the Advanced Card Selection section.

## Project Structure
The script is organized into the following modules:
- `MtgPng2Pdf.py`: The main entry point for the script.
- `card_processing.py`: Handles the logic for processing the deck list and selecting cards.
- `config.py`: Contains configuration constants.
- `image_handler.py`: Manages image discovery and handling.
- `main_logic.py`: Contains the main function and command-line argument parsing.
- `output_utils.py`: Contains functions for generating output files.
- `parsing_utils.py`: Contains parsing utilities for deck lists and filenames.
- `pdf_generator.py`: Contains functions for generating PDF files.
- `web_utils.py`: Contains functions for interacting with a web server.

## Requirements
On Debian 12, install the required packages:
```bash
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
              [--basic-land-set-mode {prefer,force,minimum}]
              [--spell-set SPELL_SET]
              [--spell-set-mode {prefer,force,minimum}]
              [--card-set CARD_SET] [--paper-type {letter,legal}]
              [--page-margin PAGE_MARGIN]
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
```

## Discovered Image Files

Before processing a deck list, `MtgPng2Pdf.py` first discovers all available card image files. These are the images that the script can potentially use to fulfill card requests from your deck list. The source of these discovered image files is determined by one of the following mutually exclusive options:

*   **Local Directory (`--png-dir`)**: If `--png-dir` is specified, the script scans this local directory (and its subdirectories) for all `.png` files. These local files become the pool of discovered images.

*   **Image Server (`--image-server-base-url`, `--image-server-path-prefix`, `--image-server-png-dir`)**: If `--image-server-base-url` is specified, the script will connect to the image server to list and potentially download image files. The full path on the server where images are expected is constructed by combining `--image-server-base-url`, `--image-server-path-prefix`, and `--image-server-png-dir`. For example, if `image-server-base-url` is `http://mtgproxy:4242`, `image-server-path-prefix` is `/local_art`, and `image-server-png-dir` is `card_images/7th`, then the script will look for images at `http://mtgproxy:4242/local_art/card_images/7th`.

These image locations can be populated using companion scripts like [ccDownloader](https://github.com/matthewddunlap/ccDownloader) (for downloading images) in combination with [scry2cc](https://github.com/matthewddunlap/scry2cc) (for generating deck lists compatible with ccDownloader).

All card selection logic (e.g., `--spell-set`, `--card-set`) operates on this pool of *discovered image files*.

## Advanced Card Selection

### Set Filtering (`--spell-set` and `--basic-land-set`)

You can control the card versions used in your PDF by filtering by set. This is done with the `--spell-set` and `--basic-land-set` arguments, which take a comma-separated list of set codes.

The behavior of this filtering is controlled by the `--spell-set-mode` and `--basic-land-set-mode` arguments, which can be one of `force`, `prefer`, or `minimum`.

*   **`force`**: Strictly use cards from the specified sets. If a card from the deck list is not found among the *discovered image files* for any of the specified sets, the card will be reported as missing and will not be included in the PDF.

*   **`prefer`**: Prioritize cards from the specified sets. If a card is available in a preferred set, it will be used. If the count for a card is not met from the preferred sets, the script will *only* use the cards from the preferred sets. Only if a card is not available in *any* of the preferred sets will the script fall back to using any available version of the card.

*   **`minimum`**: Prioritize cards from the specified sets. If a card is available in a preferred set, it will be used. If the count for a card is not met from the preferred sets, the script will use any other available versions of the card to meet the count.

When using `force`, `prefer`, or `minimum`, the order of the sets in the `--spell-set` argument matters. The script will prioritize duplicating art from the sets that appear earlier in the list.

### Per-Card Overrides (`--card-set`)

For more granular control, you can override the global set filtering for individual cards using the `--card-set` argument. This argument can be used multiple times.

The format for this argument is `"<Card Name>:<Set(s)>[:<Mode>]"`.

*   **`<Card Name>`**: The name of the card to override.
*   **`<Set(s)>`**: A comma-separated list of set codes.
*   **`<Mode>`**: (Optional) The set mode (`force`, `prefer`, or `minimum`) to use for this specific card. If not provided, the global `--spell-set-mode` is used.

#### Variant Preference

You can also use the `--card-set` argument to specify a preference for art variants within a set. This is done by appending a variant letter to the set code, like `<set>-<variant>`.

For example, to specify a preference for the art variants of Strip Mine from the Antiquities set, you would use:

`--card-set "Strip Mine:atq-c,atq-a,atq-b:force"`

This will prioritize the 'c' variant, then 'a', then 'b'.

## Examples

### Generate PDF for manual cutting
```bash
python3 MtgPng2Pdf.py --png-dir card_images/m15ub --output-format pdf --output-file myDeck.pdf --deck-list myDeck.txt --cut-lines --cut-line-width-pt 2
```

### Generate PDF for automated cutting with Silhouette Cameo
```bash
python3 MtgPng2Pdf.py --png-dir card_images/m15ub --output-format pdf --output-file myDeck.pdf --deck-list myDeck.txt --cameo
```

### Force art from specific sets
This command will only use card art from the specified sets. If a card is not available in one of these sets, it will be skipped.
```bash
python3 MtgPng2Pdf.py --image-server-base-url http://mtgproxy:4242 --image-server-path-prefix /local_art --image-server-png-dir card_images/7th/realesrgan_x2plus-4x/ --deck-list ../scry2cc/smashville-zoo.txt --cameo --cameo-label-font-size 48 --upload-to-server --image-server-pdf-dir decks --overwrite-server-file --spell-set lea,leb,arn,atq,3ed,leg,drk,fem,4ed,ice,chr,hml,all --spell-set-mode force
```

### Prioritize art from specific sets
This command will prioritize art from the specified sets, and if there are multiple art options, it will prefer duplicating the art from the sets that appear earlier in the list.
```bash
python3 MtgPng2Pdf.py --image-server-base-url http://mtgproxy:4242 --image-server-path-prefix /local_art --image-server-png-dir card_images/7th/realesrgan_x2plus-4x/ --deck-list ../scry2cc/smashville-zoo.txt --cameo --cameo-label-font-size 48 --upload-to-server --image-server-pdf-dir decks --overwrite-server-file --spell-set lea,leb,arn,atq,3ed,leg,drk,fem,4ed,ice,chr,hml,all --spell-set-mode prefer
```

### Per-card set override
This command forces the use of the Ice Age version of Disenchant.
```bash
python3 MtgPng2Pdf.py --image-server-base-url http://mtgproxy:4242 --image-server-path-prefix /local_art --image-server-png-dir card_images/7th/realesrgan_x2plus-4x/ --deck-list ../scry2cc/smashville-zoo.txt --cameo --cameo-label-font-size 48 --upload-to-server --image-server-pdf-dir decks --overwrite-server-file --spell-set lea,leb,arn,atq,3ed,leg,drk,fem,4ed,ice,chr,hml,all --spell-set-mode force --card-set "Disenchant:ice:force"
```

### Art variant preference
This command specifies the preferred order of art variants for Strip Mine from the Antiquities set.
```bash
python3 MtgPng2Pdf.py --image-server-base-url http://mtgproxy:4242 --image-server-path-prefix /local_art --image-server-png-dir card_images/7th/realesrgan_x2plus-4x/ --deck-list ../scry2cc/smashville-zoo.txt --cameo --cameo-label-font-size 48 --upload-to-server --image-server-pdf-dir decks --overwrite-server-file --spell-set lea,leb,arn,atq,3ed,leg,drk,fem,4ed,ice,chr,hml,all --spell-set-mode force --card-set "Strip Mine:atq-c,atq-a,atq-b:force"
```