"""문제 그림(img/problem.jpg)의 빈 말풍선에 짧은 독자 항의 문구를 얹어 img/problem-text.jpg 를 만들어요.

이미지 모델은 한글을 정확히 그리지 못해서, 그림은 그대로 두고 글자만 Pillow로 덧그려요.
    python docs/proposal/label_problem.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"  # 인덱스 1 = KR
INK, RED = (35, 40, 60), (192, 57, 43)
# 말풍선 안쪽 영역(img/problem.jpg 1600x483 기준)과 두 줄 문구. [강조]는 빨간색.
BUBBLES = [((1222, 62, 1432, 178), ["책대로 했는데", "[오류]가 나요"]),
           ((1222, 232, 1432, 348), ["API가 바뀌었어요", "[환불]해 주세요!"])]


def draw_line(d, x, y, text, font):
    for i, part in enumerate(text.replace("]", "[").split("[")):
        d.text((x, y), part, font=font, fill=RED if i % 2 else INK)
        x += d.textlength(part, font=font)


def main():
    im = Image.open(HERE / "img/problem.jpg").convert("RGB")
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(FONT, 27, index=1)
    for (x0, y0, x1, y1), lines in BUBBLES:
        d.rectangle((x0, y0, x1, y1), fill="white")  # 큰 느낌표 지우기
        widths = [d.textlength(line.replace("[", "").replace("]", ""), font=font) for line in lines]
        line_h = 38
        top = (y0 + y1) / 2 - line_h * len(lines) / 2 - 4
        for n, (line, w) in enumerate(zip(lines, widths)):
            draw_line(d, (x0 + x1) / 2 - w / 2, top + n * line_h, line, font)
    im.save(HERE / "img/problem-text.jpg", quality=88, optimize=True)
    print("img/problem-text.jpg")


if __name__ == "__main__":
    main()
