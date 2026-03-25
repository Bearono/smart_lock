import smtplib
import datetime
import time
from email.mime.text import MIMEText
from email.header import Header
from io import BytesIO
from PIL import Image, ImageDraw

global_frame_bytes = None
global_image_obj = None


def add_watermark(image_bytes):
    try:
        image = Image.open(BytesIO(image_bytes))
        draw = ImageDraw.Draw(image)
        text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        draw.text((10, 10), text, fill=(255, 0, 0))
        return image
    except Exception as e:
        print(f"水印添加失败: {e}")
        return None


def send_email(config, alarm_type, message):
    try:
        subject = f"【紧急】智能门锁报警：{alarm_type}"
        content = f"检测时间：{datetime.datetime.now()}\n详情：{message}"

        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = config['SENDER_EMAIL']
        msg['To'] = config['RECEIVER_EMAIL']

        smtp = smtplib.SMTP_SSL(config['SMTP_SERVER'], config['SMTP_PORT'])
        smtp.login(config['SENDER_EMAIL'], config['SENDER_PASSWORD'])
        smtp.sendmail(config['SENDER_EMAIL'], config['RECEIVER_EMAIL'], msg.as_string())
        smtp.quit()
        print("邮件已发送")
    except Exception as e:
        print(f"邮件发送失败: {e}")


def generate_video_stream():
    global global_frame_bytes
    while True:
        if global_frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + global_frame_bytes + b'\r\n')
        time.sleep(0.05)