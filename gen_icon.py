from PIL import Image, ImageDraw

def create_icon():
    # Create a nice 256x256 icon
    size = (256, 256)
    image = Image.new('RGBA', size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    
    # Background Circle
    dc.ellipse([10, 10, 246, 246], fill=(14, 22, 41), outline=(6, 182, 212), width=8)
    
    # Star/Magic shape (approximate)
    center = 128
    points = [
        (128, 48), (146, 102), (196, 102), (154, 134), 
        (170, 188), (128, 156), (86, 188), (102, 134), 
        (60, 102), (110, 102)
    ]
    dc.polygon(points, fill=(6, 182, 212))
    
    # Save as ICO with multiple sizes
    image.save('static/favicon.ico', format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
    print("Created static/favicon.ico")

if __name__ == "__main__":
    create_icon()
