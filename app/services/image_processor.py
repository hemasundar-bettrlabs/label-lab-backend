from PIL import Image, ImageDraw
import io
import base64
import math

def decode_image_from_base64(base64_string: str) -> Image.Image:
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    image_data = base64.b64decode(base64_string)
    return Image.open(io.BytesIO(image_data))

def encode_image_to_base64(image: Image.Image) -> str:
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_str}"

def add_grid_overlay(base64_image: str) -> str:
    """
    Adds a 10x10 grid overlay to the image for spatial reference.
    Matches the frontend implementation logic.
    """
    try:
        if not base64_image:
            return ""
            
        img = decode_image_from_base64(base64_image)
        # Convert to RGB if not
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        width, height = img.size
        draw = ImageDraw.Draw(img)
        
        # Grid settings - Red color, semitransparent look simulated by thin lines
        # PIL doesn't support alpha on draw.line directly easily without RGBA
        # For simplicity, we use solid red lines.
        grid_color = (255, 0, 0)
        
        # 10x10 Grid
        cols = 10
        rows = 10
        
        step_x = width / cols
        step_y = height / rows
        
        # Draw vertical lines
        for i in range(1, cols):
            x = int(i * step_x)
            draw.line([(x, 0), (x, height)], fill=grid_color, width=2)
            
            # Add coordinates (Top edge)
            # draw.text((x + 5, 5), f"{i*10}", fill=grid_color)

        # Draw horizontal lines
        for i in range(1, rows):
            y = int(i * step_y)
            draw.line([(0, y), (width, y)], fill=grid_color, width=2)
            
            # Add coordinates (Left edge)
            # draw.text((5, y + 5), f"{i*10}", fill=grid_color)

        # Draw border
        draw.rectangle([(0, 0), (width-1, height-1)], outline=grid_color, width=4)
        
        return encode_image_to_base64(img)
        
    except Exception as e:
        print(f"Error adding grid overlay: {e}")
        return base64_image # Return original if failure
