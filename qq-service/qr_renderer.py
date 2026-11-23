"""Render QQ login QR codes locally; no external QR service or runtime."""
class QRRenderer:
    def svg(self, text):
        import qrcode
        from qrcode.image.svg import SvgPathImage
        qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=4,border=4)
        qr.add_data(text)
        qr.make(fit=True)
        return qr.make_image(image_factory=SvgPathImage).to_string()
