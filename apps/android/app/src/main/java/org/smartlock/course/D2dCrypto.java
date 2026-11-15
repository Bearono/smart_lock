package org.smartlock.course;

import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.ECParameterSpec;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.Timer;
import java.util.TimerTask;
import java.util.function.LongSupplier;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

/** Explicitly pinned, single-session audio coursework receiver. No keys are persisted. */
public final class D2dCrypto {
    public static final String VERSION = "SL-AUDIO-D2D-1";
    private static final int MAX_WIRE_BYTES = 2048;
    private static final Set<String> BINDING_KEYS = keys(
            "version", "sender", "recipient", "session", "challenge", "expires");
    private final SecureRandom random = new SecureRandom();
    private final LongSupplier clock;
    private Map<String, Object> binding;
    private PrivateKey recipientPrivate;
    private PublicKey recipientPublic;
    private PublicKey issuerPublic;
    private byte[] sessionKey;
    private long expires;
    private Timer expiryTimer;

    public D2dCrypto() { this(() -> System.currentTimeMillis() / 1000L); }

    // Package-private clock seam supports expiry tests without changing device time.
    D2dCrypto(LongSupplier clock) { this.clock = clock; }

    public synchronized String beginRequest(String issuerId, String receiverId,
                                             String pinnedIssuerSpkiBase64)
            throws GeneralSecurityException {
        clear();
        identity(issuerId);
        identity(receiverId);
        if (issuerId.equals(receiverId)) throw new IllegalArgumentException("Identities must differ");
        PublicKey issuer = KeyFactory.getInstance("EC").generatePublic(
                new X509EncodedKeySpec(decode64(pinnedIssuerSpkiBase64, 256)));
        requireP256(issuer);
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048, random);
        KeyPair receiver = generator.generateKeyPair();
        long now = clock.getAsLong();
        if (now < 0 || now > Long.MAX_VALUE - 300) throw new IllegalArgumentException("Invalid system time");
        Map<String, Object> fresh = new TreeMap<>();
        fresh.put("version", VERSION);
        fresh.put("sender", issuerId);
        fresh.put("recipient", receiverId);
        fresh.put("session", randomHex());
        fresh.put("challenge", randomHex());
        fresh.put("expires", now + 180);
        Map<String, Object> request = new TreeMap<>(fresh);
        request.put("recipient_public_key", encode64(receiver.getPublic().getEncoded()));
        String encoded = boundedJson(request);
        binding = fresh;
        recipientPrivate = receiver.getPrivate();
        recipientPublic = receiver.getPublic();
        issuerPublic = issuer;
        expires = now + 180;
        expiryTimer = new Timer("SmartLock audio session expiry", true);
        expiryTimer.schedule(new TimerTask() {
            @Override public void run() {
                synchronized (D2dCrypto.this) {
                    if (binding == fresh) clear();
                }
            }
        }, 180000L);
        return encoded;
    }

    public synchronized String recipientPublicKeyBase64() throws GeneralSecurityException {
        requireAlive(false);
        return encode64(recipientPublic.getEncoded());
    }

    public synchronized void acceptPacket(String packetJson) throws GeneralSecurityException {
        requireAlive(false);
        if (sessionKey != null || recipientPrivate == null)
            throw new GeneralSecurityException("Session packet already accepted");
        Map<String, Object> packet = parseObject(packetJson);
        exactKeys(packet, keys("binding", "wrapped", "signature"));
        Map<String, Object> supplied = object(packet.get("binding"));
        validateBinding(supplied);
        if (!binding.equals(supplied)) throw new GeneralSecurityException("Pending request binding mismatch");
        byte[] wrapped = decode64(string(packet.get("wrapped")), 256);
        if (wrapped.length != 256) throw new GeneralSecurityException("Expected RSA-2048 ciphertext");
        byte[] signature = decode64(string(packet.get("signature")), 80);
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(issuerPublic);
        verifier.update(bytes("smartlock/audio-d2d/v1\0"));
        verifier.update(bytes(json(binding)));
        verifier.update(wrapped);
        if (!verifier.verify(signature)) throw new GeneralSecurityException("Issuer signature rejected");
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        cipher.init(Cipher.DECRYPT_MODE, recipientPrivate, new OAEPParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                new PSource.PSpecified(bytes("smart-lock/course/key-wrap/v1"))));
        byte[] key = cipher.doFinal(wrapped);
        if (key.length != 32) {
            Arrays.fill(key, (byte) 0);
            throw new GeneralSecurityException("Distributed key must be AES-256");
        }
        // The deadline can pass while an expensive public-key operation is running.
        try { requireAlive(false); }
        catch (GeneralSecurityException error) { Arrays.fill(key, (byte) 0); throw error; }
        sessionKey = key;
        recipientPrivate = null;
    }

    public synchronized String confirmationJson() throws GeneralSecurityException {
        requireAlive(true);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(sessionKey, "HmacSHA256"));
        mac.update(bytes("smartlock/audio-confirm/v1\0"));
        byte[] proof = mac.doFinal(bytes(json(binding)));
        Map<String, Object> result = new TreeMap<>();
        result.put("binding", binding);
        result.put("type", "confirm");
        result.put("proof", encode64(proof));
        return boundedJson(result);
    }

    public synchronized String encryptMessage(String plaintext) throws GeneralSecurityException {
        requireAlive(true);
        if (plaintext == null) throw new IllegalArgumentException("Message required");
        byte[] content = bytes(plaintext);
        if (content.length == 0 || content.length > 1024)
            throw new IllegalArgumentException("Use 1..1024 UTF-8 message bytes");
        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(sessionKey, "AES"), new GCMParameterSpec(128, nonce));
        cipher.updateAAD(bytes("smartlock/audio-message/v1\0"));
        cipher.updateAAD(bytes(json(binding)));
        byte[] ciphertext = cipher.doFinal(content);
        Map<String, Object> result = new TreeMap<>();
        result.put("binding", binding);
        result.put("type", "message");
        result.put("nonce", encode64(nonce));
        result.put("ciphertext", encode64(ciphertext));
        return boundedJson(result);
    }

    public synchronized boolean hasSession() {
        if (expires <= clock.getAsLong()) clear();
        return sessionKey != null;
    }

    public synchronized long expiresAtEpochSeconds() {
        if (expires <= clock.getAsLong()) clear();
        return expires;
    }

    public synchronized void clear() {
        if (expiryTimer != null) expiryTimer.cancel();
        expiryTimer = null;
        if (sessionKey != null) Arrays.fill(sessionKey, (byte) 0);
        sessionKey = null;
        recipientPrivate = null;
        recipientPublic = null;
        issuerPublic = null;
        binding = null;
        expires = 0;
    }

    private void requireAlive(boolean established) throws GeneralSecurityException {
        long now = clock.getAsLong();
        if (binding == null || now < 0 || now >= expires || expires - now > 300) {
            clear();
            throw new GeneralSecurityException("Session missing or expired; create a new request");
        }
        if (established && sessionKey == null) throw new GeneralSecurityException("Accept a verified session packet first");
    }

    private void validateBinding(Map<String, Object> value) throws GeneralSecurityException {
        exactKeys(value, BINDING_KEYS);
        if (!VERSION.equals(value.get("version"))) throw new GeneralSecurityException("Unsupported version");
        identity(string(value.get("sender")));
        identity(string(value.get("recipient")));
        for (String key : new String[]{"session", "challenge"})
            if (!string(value.get(key)).matches("[0-9a-f]{32}")) throw new GeneralSecurityException("Invalid session binding");
        if (!(value.get("expires") instanceof Long)) throw new GeneralSecurityException("Expiration must be an integer");
        long end = (Long) value.get("expires");
        long now = clock.getAsLong();
        if (end <= now || end - now > 300) throw new GeneralSecurityException("Packet expired or lifetime too long");
    }

    private String randomHex() {
        byte[] value = new byte[16];
        random.nextBytes(value);
        StringBuilder output = new StringBuilder(32);
        for (byte item : value) output.append(String.format(java.util.Locale.ROOT, "%02x", item & 255));
        return output.toString();
    }

    private static void requireP256(PublicKey key) throws GeneralSecurityException {
        if (!(key instanceof ECPublicKey)) throw new GeneralSecurityException("Pinned issuer must use P-256");
        AlgorithmParameters parameters = AlgorithmParameters.getInstance("EC");
        parameters.init(new ECGenParameterSpec("secp256r1"));
        ECParameterSpec expected = parameters.getParameterSpec(ECParameterSpec.class);
        ECParameterSpec actual = ((ECPublicKey) key).getParams();
        if (!expected.getCurve().equals(actual.getCurve()) || !expected.getGenerator().equals(actual.getGenerator())
                || !expected.getOrder().equals(actual.getOrder()) || expected.getCofactor() != actual.getCofactor())
            throw new GeneralSecurityException("Pinned issuer must use P-256");
    }

    private static void identity(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,50}"))
            throw new IllegalArgumentException("Identity must contain 1..50 ASCII letters, digits, _ or -");
    }

    private static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    private static String encode64(byte[] value) { return Base64.getEncoder().encodeToString(value); }
    private static byte[] decode64(String value, int maximum) {
        if (value == null || value.length() > ((maximum + 2) / 3) * 4)
            throw new IllegalArgumentException("Oversized base64 value");
        byte[] decoded = Base64.getDecoder().decode(value);
        if (decoded.length > maximum || !encode64(decoded).equals(value))
            throw new IllegalArgumentException("Expected canonical padded base64");
        return decoded;
    }

    private static String string(Object value) {
        if (!(value instanceof String)) throw new IllegalArgumentException("Expected a JSON string");
        return (String) value;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> object(Object value) {
        if (!(value instanceof Map)) throw new IllegalArgumentException("Expected a JSON object");
        return (Map<String, Object>) value;
    }

    private static void exactKeys(Map<String, Object> value, Set<String> expected) {
        if (!value.keySet().equals(expected)) throw new IllegalArgumentException("Unexpected or missing JSON fields");
    }

    private static Set<String> keys(String... names) { return new HashSet<>(Arrays.asList(names)); }

    private static String boundedJson(Map<String, Object> value) {
        String encoded = json(value);
        if (bytes(encoded).length > MAX_WIRE_BYTES) throw new IllegalArgumentException("Packet exceeds audio payload limit");
        return encoded;
    }

    // All protocol values are ASCII strings, integer timestamps, or nested objects.
    // A small strict codec avoids Android-only JSON dependencies in JVM interop tests.
    static String json(Map<String, Object> value) {
        StringBuilder result = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> field : new TreeMap<>(value).entrySet()) {
            if (!first) result.append(',');
            first = false;
            result.append(quote(field.getKey())).append(':');
            Object item = field.getValue();
            if (item instanceof String) result.append(quote((String) item));
            else if (item instanceof Long) result.append(item);
            else if (item instanceof Map) result.append(json(object(item)));
            else throw new IllegalArgumentException("Unsupported JSON value");
        }
        return result.append('}').toString();
    }

    private static String quote(String value) {
        StringBuilder result = new StringBuilder("\"");
        for (char ch : value.toCharArray()) {
            if (ch == '\\' || ch == '"') result.append('\\').append(ch);
            else if (ch < 32 || ch > 126) {
                String hex = Integer.toHexString(ch);
                result.append("\\u");
                for (int i = hex.length(); i < 4; i++) result.append('0');
                result.append(hex);
            } else result.append(ch);
        }
        return result.append('"').toString();
    }

    static Map<String, Object> parseObject(String input) {
        if (input == null || bytes(input).length > MAX_WIRE_BYTES) throw new IllegalArgumentException("Invalid packet size");
        Parser parser = new Parser(input);
        Map<String, Object> value = parser.readObject(0);
        parser.whitespace();
        if (parser.offset != input.length()) throw new IllegalArgumentException("Trailing JSON data");
        return value;
    }

    private static final class Parser {
        final String input;
        int offset;
        Parser(String input) { this.input = input; }
        void whitespace() {
            while (offset < input.length() && " \n\r\t".indexOf(input.charAt(offset)) >= 0) offset++;
        }
        char take() {
            if (offset >= input.length()) throw new IllegalArgumentException("Truncated JSON");
            return input.charAt(offset++);
        }
        void expect(char expected) {
            whitespace();
            if (take() != expected) throw new IllegalArgumentException("Malformed JSON");
        }
        Map<String, Object> readObject(int depth) {
            if (depth > 1) throw new IllegalArgumentException("Nested JSON exceeds protocol shape");
            expect('{');
            Map<String, Object> result = new LinkedHashMap<>();
            whitespace();
            if (offset < input.length() && input.charAt(offset) == '}') { offset++; return result; }
            while (true) {
                whitespace();
                String key = readString();
                if (result.containsKey(key)) throw new IllegalArgumentException("Duplicate JSON field");
                expect(':');
                whitespace();
                if (offset >= input.length()) throw new IllegalArgumentException("Truncated JSON");
                char start = input.charAt(offset);
                Object value;
                if (start == '"') value = readString();
                else if (start == '{') value = readObject(depth + 1);
                else value = readInteger();
                result.put(key, value);
                whitespace();
                char separator = take();
                if (separator == '}') return result;
                if (separator != ',') throw new IllegalArgumentException("Malformed JSON object");
            }
        }
        String readString() {
            if (take() != '"') throw new IllegalArgumentException("Expected JSON string");
            StringBuilder result = new StringBuilder();
            while (true) {
                char ch = take();
                if (ch == '"') return result.toString();
                if (ch < 32) throw new IllegalArgumentException("Control character in JSON string");
                if (ch == '\\') {
                    ch = take();
                    if (ch == '"' || ch == '\\' || ch == '/') result.append(ch);
                    else if (ch == 'u') {
                        if (offset + 4 > input.length()) throw new IllegalArgumentException("Truncated Unicode escape");
                        String digits = input.substring(offset, offset + 4);
                        if (!digits.matches("[0-9A-Fa-f]{4}")) throw new IllegalArgumentException("Invalid Unicode escape");
                        result.append((char) Integer.parseInt(digits, 16));
                        offset += 4;
                    } else throw new IllegalArgumentException("Unsupported protocol string escape");
                } else result.append(ch);
            }
        }
        Long readInteger() {
            int start = offset;
            if (offset < input.length() && input.charAt(offset) == '-') offset++;
            while (offset < input.length() && input.charAt(offset) >= '0' && input.charAt(offset) <= '9') offset++;
            String number = input.substring(start, offset);
            if (!number.matches("-?(0|[1-9][0-9]*)")) throw new IllegalArgumentException("Expected integer timestamp");
            try { return Long.valueOf(number); }
            catch (NumberFormatException error) { throw new IllegalArgumentException("Timestamp outside range", error); }
        }
    }
}
