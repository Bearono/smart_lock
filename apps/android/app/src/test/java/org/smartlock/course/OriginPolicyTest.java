package org.smartlock.course;

import org.junit.Test;
import static org.junit.Assert.*;
import java.nio.ByteBuffer;
import java.util.Base64;

public class OriginPolicyTest {
    @Test public void acceptsExactHttpsOrigin() {
        OriginPolicy policy = new OriginPolicy("https://LOCK.example:8443/");
        assertEquals("https://lock.example:8443", policy.origin());
        assertTrue(policy.allows("https://lock.example:8443/dashboard?tab=1"));
        assertTrue(new OriginPolicy("https://lock.example").allows("https://lock.example:443/api"));
    }
    @Test public void rejectsHostConfusionCredentialsAndActiveSchemes() {
        OriginPolicy policy = new OriginPolicy("https://lock.example:8443");
        for (String url : new String[] {"http://lock.example:8443", "https://lock.example.evil:8443",
                "https://lock.example:8443@evil.example", "https://evil@lock.example:8443/",
                "https://lock.example/", "https://lock.example:8444/", "javascript:alert(1)",
                "file:///sdcard/passwords", "content://lock.example", "https://lock.example\\@evil:8443/", null})
            assertFalse(String.valueOf(url), policy.allows(url));
    }
    @Test public void configurationMustBeAnOrigin() {
        for (String url : new String[] {"", "http://lock.example", "https://lock.example/path",
                "https://user:password@lock.example", "https://lock.example?key=1",
                "https://lock.example#secret", "https://lock.example:0", "https://lock.example:65536"})
            assertThrows(url, IllegalArgumentException.class, () -> new OriginPolicy(url));
    }
    @Test public void onlyBoundedPngDataImagesAreAllowed() {
        String png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jF1sAAAAASUVORK5CYII=";
        assertNotNull(OriginPolicy.inlinePng(png));
        assertNull(OriginPolicy.inlinePng(png.replace("image/png", "text/html")));
        assertNull(OriginPolicy.inlinePng("data:image/png;base64,PGh0bWw+"));
        assertNull(OriginPolicy.inlinePng("data:image/svg+xml,<svg/>"));
        assertNull(OriginPolicy.inlinePng("data:image/png;base64," + "A".repeat(524288)));
        byte[] oversized = OriginPolicy.inlinePng(png);
        ByteBuffer.wrap(oversized).putInt(16, 100000);
        assertNull(OriginPolicy.inlinePng("data:image/png;base64," + Base64.getEncoder().encodeToString(oversized)));
    }
}
