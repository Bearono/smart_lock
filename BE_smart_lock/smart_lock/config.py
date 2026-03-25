import os


class Config:
    # 数据库配置：用户名:密码@地址/数据库名
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:1539478578w@localhost/smart_lock_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 安全密钥
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'secret-key-123'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-456'

    # 抓拍图片存储路径
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'app/static/captures')

    # 邮件配置（使用对方提供的配置）
    SMTP_SERVER = "smtp.qq.com"
    SMTP_PORT = 465
    SENDER_EMAIL = "3379591910@qq.com"
    SENDER_PASSWORD = "cwmsujlzeqldchfd"
    RECEIVER_EMAIL = "3379591910@qq.com"