from app import create_app

app = create_app()

if __name__ == '__main__':
    # host='0.0.0.0' 让局域网内的前端可以访问
    app.run(host='127.0.0.1', port=8000, debug=False)
