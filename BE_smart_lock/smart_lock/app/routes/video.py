import datetime
from io import BytesIO
from flask import Blueprint, request, Response, render_template_string, current_app, url_for
from app import utils

# 创建视频蓝图
video_bp = Blueprint('video', __name__)

@video_bp.route('/api/upload_frame', methods=['POST'])
def upload_frame():
    """接收硬件上传的视频帧"""
    file = request.files.get('file')
    if file:
        raw_bytes = file.read()
        processed_img = utils.add_watermark(raw_bytes)
        if processed_img:
            utils.global_image_obj = processed_img
            img_byte_arr = BytesIO()
            processed_img.save(img_byte_arr, format='JPEG')
            utils.global_frame_bytes = img_byte_arr.getvalue()
        return "Frame received", 200
    return "No file", 400

@video_bp.route('/video_feed')
def video_feed():
    """实时视频流输出"""
    return Response(utils.generate_video_stream(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@video_bp.route('/')
def index():
    """监控后台主页"""
    # 使用 url_for 动态生成路径，解决 404 问题
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>智能门锁监控中心</title>
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: white; padding: 20px; margin: 0; }
                .container { max-width: 1000px; margin: 0 auto; display: grid; grid-template-columns: 1fr 300px; gap: 20px; }
                .video-box { background: #1e293b; padding: 15px; border-radius: 12px; text-align: center; }
                .video-box img { max-width: 100%; border: 2px solid #334155; border-radius: 4px; }
                .log-box { background: #1e293b; padding: 15px; border-radius: 12px; height: 600px; overflow-y: auto; }
                .log-item { background: #334155; padding: 10px; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid #ef4444; }
                .log-time { font-size: 11px; color: #94a3b8; }
                .log-img { width: 100%; height: 60px; object-fit: cover; margin-top: 5px; border-radius: 4px; }
                h2 { margin-top: 0; font-size: 18px; border-bottom: 1px solid #334155; padding-bottom: 10px; }
            </style>
        </head>
        <body>
            <h1 style="text-align:center;">🔐 智能门锁安全监控</h1>
            <div class="container">
                <div class="video-box">
                    <div style="margin-bottom:10px; color:#22c55e;">● LIVE 实时监控中</div>
                    <img src="{{ url_for('video.video_feed') }}" />
                </div>
                <div class="log-box">
                    <h2>🚨 报警记录</h2>
                    <div id="log-list">正在加载...</div>
                </div>
            </div>
            <script>
                function fetchAlarms() {
                    // 注意：这里需要指向 alarm 蓝图下的接口
                    fetch('/api/alarms') 
                    .then(res => res.json())
                    .then(data => {
                        const list = document.getElementById('log-list');
                        list.innerHTML = data.map(log => `
                            <div class="log-item">
                                <div class="log-time">${log.time}</div>
                                <div style="font-weight:bold; color:#fca5a5;">${log.type}</div>
                                <div style="font-size:13px;">${log.message}</div>
                                ${log.snapshot !== '无画面' ? `<img class="log-img" src="${log.snapshot}">` : ''}
                            </div>
                        `).join('');
                    });
                }
                setInterval(fetchAlarms, 3000);
                fetchAlarms();
            </script>
        </body>
        </html>
    ''')