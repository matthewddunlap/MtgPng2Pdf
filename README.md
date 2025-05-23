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

## Examples
###Generate PDF for manual cutting
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
