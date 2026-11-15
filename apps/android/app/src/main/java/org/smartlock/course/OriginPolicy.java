package org.smartlock.course;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.Base64;
import java.nio.ByteBuffer;

/** Exact HTTPS origin allowlist; configuration never contains credentials or paths. */
public final class OriginPolicy {
    private final String host;
    private final int port;
    private final String origin;

    public OriginPolicy(String value) {
        URI uri = parse(value == null ? "" : value.trim());
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                || uri.getRawFragment() != null || uri.getPort() == 0 || uri.getPort() > 65535
                || !(uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException("请输入完整 HTTPS 服务地址，不包含账号、路径或查询参数");
        }
        host = uri.getHost().toLowerCase(Locale.ROOT);
        port = uri.getPort() == -1 ? 443 : uri.getPort();
        origin = "https://" + host + (port == 443 ? "" : ":" + port);
    }

    public String origin() { return origin; }

    public boolean allows(String value) {
        try {
            URI uri = parse(value);
            return "https".equalsIgnoreCase(uri.getScheme()) && uri.getRawUserInfo() == null
                    && host.equalsIgnoreCase(uri.getHost())
                    && (uri.getPort() == -1 ? 443 : uri.getPort()) == port;
        } catch (IllegalArgumentException ignored) { return false; }
    }

    /** Only bounded PNG data images, used for the server's TOTP enrollment QR. */
    public static byte[] inlinePng(String value) {
        final String prefix = "data:image/png;base64,";
        if (value == null || !value.startsWith(prefix) || value.length() > 524288) return null;
        try {
            byte[] image = Base64.getDecoder().decode(value.substring(prefix.length()));
            byte[] signature = {(byte) 137, 80, 78, 71, 13, 10, 26, 10};
            if (image.length < 33) return null;
            for (int i = 0; i < signature.length; i++) if (image[i] != signature[i]) return null;
            ByteBuffer header = ByteBuffer.wrap(image);
            if (header.getInt(8) != 13 || header.getInt(12) != 0x49484452) return null;
            int width = header.getInt(16), height = header.getInt(20);
            return width > 0 && width <= 2048 && height > 0 && height <= 2048 ? image : null;
        } catch (IllegalArgumentException error) { return null; }
    }

    private static URI parse(String value) {
        try {
            if (value == null || value.indexOf('\\') >= 0) throw new URISyntaxException("", "backslash");
            return new URI(value);
        } catch (URISyntaxException error) {
            throw new IllegalArgumentException("无效的 HTTPS 地址", error);
        }
    }
}
