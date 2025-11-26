from PIL import Image, ImageDraw, ImageFont
import os
import textwrap
from typing import Dict

def generate_deck_manifest_image(
    selection_manifest: Dict[str, Dict[str, Dict[str, int]]],
    font_size: int,
    output_path: str,
    deck_name: str,
    image_width: int = 1005,
    image_height: int = 1407
):
    """
    Generates a PNG image with the deck manifest.

    Args:
        selection_manifest: A dictionary representing the deck manifest.
        font_size: The font size for the manifest text. If 0, auto-sizes the font.
        output_path: The path to save the generated PNG image.
        deck_name: The name of the deck to display as the title.
        image_width: The width of the output image.
        image_height: The height of the output image.
    """
    # Create a new image with a white background
    img = Image.new('RGB', (image_width, image_height), color = 'white')
    d = ImageDraw.Draw(img)

    # Prepare the text
    # Replace dashes and underscores with spaces, then capitalize each word
    formatted_deck_name = deck_name.replace('-', ' ').replace('_', ' ')
    title = " ".join([word.capitalize() for word in formatted_deck_name.split()])
    manifest_text = f"{title}\n\n"

    if selection_manifest.get("Deck"):
        manifest_text += "Deck\n"
        for card_name, versions in sorted(selection_manifest["Deck"].items()):
            total_count = sum(versions.values())
            manifest_text += f"  {total_count}x {card_name}\n"
        manifest_text += "\n"

    if selection_manifest.get("Sideboard"):
        manifest_text += "Sideboard\n"
        for card_name, versions in sorted(selection_manifest["Sideboard"].items()):
            total_count = sum(versions.values())
            manifest_text += f"  {total_count}x {card_name}\n"
        manifest_text += "\n"

    if selection_manifest.get("Token"):
        manifest_text += "Token\n"
        for card_name, versions in sorted(selection_manifest["Token"].items()):
            total_count = sum(versions.values())
            manifest_text += f"  {total_count}x {card_name}\n"

    font_path = os.path.join(os.path.dirname(__file__), 'assets', 'DejaVuSans.ttf')

    # Auto-size font if requested
    if font_size == 0:
        max_font_size = 96
        min_font_size = 8
        
        best_font_size = min_font_size
        final_wrapped_text = ""
        
        for size in range(max_font_size, min_font_size - 1, -1):
            try:
                font = ImageFont.truetype(font_path, size)
            except IOError:
                font = ImageFont.load_default()

            # Wrap text
            lines = []
            for line in manifest_text.split('\n'):
                if not line:
                    lines.append('')
                    continue
                
                # A bit of a hack to estimate the number of chars per line
                try:
                    avg_char_width = font.getlength('a')
                except AttributeError:
                    avg_char_width = font.getbbox('a')[2]
                
                chars_per_line = int((image_width - 120) / avg_char_width) if avg_char_width > 0 else 1
                
                wrapped = textwrap.wrap(line, width=chars_per_line)
                lines.extend(wrapped)
            
            wrapped_text = "\n".join(lines)
            bbox = d.multiline_textbbox((60, 50), wrapped_text, font=font)

            if bbox[3] < image_height - 50:
                best_font_size = size
                final_wrapped_text = wrapped_text
                break
        
        font_size = best_font_size
        manifest_text = final_wrapped_text

    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        font = ImageFont.load_default()

    # Final wrap with the chosen font size
    if font_size != 0: # if font size was specified, we need to wrap the text
        lines = []
        for line in manifest_text.split('\n'):
            if not line:
                lines.append('')
                continue
            try:
                avg_char_width = font.getlength('a')
            except AttributeError:
                avg_char_width = font.getbbox('a')[2]
            chars_per_line = int((image_width - 120) / avg_char_width) if avg_char_width > 0 else 1
            wrapped = textwrap.wrap(line, width=chars_per_line)
            lines.extend(wrapped)
        final_text = "\n".join(lines)
    else: # if font size was auto-detected, text is already wrapped
        final_text = manifest_text

    # Draw the text on the image
    d.text((60,50), final_text, fill=(0,0,0), font=font)

    # Save the image
    img.save(output_path)
