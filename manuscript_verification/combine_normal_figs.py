from PIL import Image

img_p = Image.open(r'figures/raw_source_assets\page1_img3_1261.jpeg')
img_l = Image.open(r'figures/raw_source_assets\page1_img4_1265.jpeg')

w = max(img_p.width, img_l.width)
gap = 30
h = img_p.height + img_l.height + gap

canvas = Image.new('RGB', (w, h), (255, 255, 255))
canvas.paste(img_p, (0, 0))
canvas.paste(img_l, (0, img_p.height + gap))
canvas.save(r'figures\fig_e1_normal.png', dpi=(300, 300))
print('Saved fig_e1_normal.png:', canvas.size)
