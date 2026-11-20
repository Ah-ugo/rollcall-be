import io, base64, secrets, qrcode

def new_token(n: int = 9) -> str:
    return secrets.token_urlsafe(n)

def qr_data_url(url: str) -> str:
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
