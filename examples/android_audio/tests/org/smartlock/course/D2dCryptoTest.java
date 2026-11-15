package org.smartlock.course;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicLong;
import javax.crypto.Cipher;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

/** Plain JVM tests: no Android runtime or third-party JSON/test dependency. */
public final class D2dCryptoTest {
    private static int checks;

    private static void check(boolean condition, String name) {
        if (!condition) throw new AssertionError(name);
        checks++;
    }

    @FunctionalInterface private interface Operation { void run() throws Exception; }
    private static void rejected(Operation operation, String name) throws Exception {
        try { operation.run(); }
        catch (GeneralSecurityException | IllegalArgumentException expected) { checks++; return; }
        throw new AssertionError("Unexpected acceptance: " + name);
    }

    private static KeyPair issuer() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"));
        return generator.generateKeyPair();
    }

    private static String b64(byte[] value) { return Base64.getEncoder().encodeToString(value); }
    private static byte[] un64(Object value) { return Base64.getDecoder().decode((String) value); }
    private static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }

    private static String issue(String request, KeyPair issuer, byte[] key, String label) throws Exception {
        Map<String, Object> binding = new TreeMap<>(D2dCrypto.parseObject(request));
        byte[] publicBytes = un64(binding.remove("recipient_public_key"));
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        cipher.init(Cipher.ENCRYPT_MODE, KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(publicBytes)),
                new OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, new PSource.PSpecified(bytes(label))));
        byte[] wrapped = cipher.doFinal(key);
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(issuer.getPrivate());
        signer.update(bytes("smartlock/audio-d2d/v1\0"));
        signer.update(bytes(D2dCrypto.json(binding)));
        signer.update(wrapped);
        Map<String, Object> packet = new TreeMap<>();
        packet.put("binding", binding);
        packet.put("wrapped", b64(wrapped));
        packet.put("signature", b64(signer.sign()));
        return D2dCrypto.json(packet);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> binding(Map<String, Object> packet) {
        return (Map<String, Object>) packet.get("binding");
    }

    private static void unitTests() throws Exception {
        KeyPair issuer = issuer();
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);
        AtomicLong now = new AtomicLong(1000);
        D2dCrypto receiver = new D2dCrypto(now::get);
        String request = receiver.beginRequest("operator", "phone_01", b64(issuer.getPublic().getEncoded()));
        String packet = issue(request, issuer, secret, "smart-lock/course/key-wrap/v1");
        check(receiver.expiresAtEpochSeconds() == 1180, "request expiration");
        check(!receiver.hasSession(), "pending is not established");
        rejected(receiver::confirmationJson, "unestablished confirmation");
        rejected(() -> receiver.encryptMessage("hello"), "unestablished message");
        rejected(() -> new D2dCrypto(now::get).acceptPacket(packet), "unsolicited packet");
        rejected(() -> receiver.acceptPacket(packet.replace("phone_01", "phone_02")), "identity binding");
        rejected(() -> receiver.acceptPacket(packet.replace("1180", "1180.0")), "float timestamp");
        rejected(() -> receiver.acceptPacket(packet.replace("1180", "1301")), "oversized lifetime");
        rejected(() -> receiver.acceptPacket(packet.replace("1180", "999")), "expired packet");
        rejected(() -> receiver.acceptPacket(packet.replace("\"signature\":", "\"extra\":\"x\",\"signature\":")), "extra field");
        rejected(() -> receiver.acceptPacket("{\"binding\":{},\"binding\":{}}"), "duplicate fields");
        rejected(() -> receiver.acceptPacket(issue(request, issuer(), secret, "smart-lock/course/key-wrap/v1")), "wrong issuer");
        rejected(() -> receiver.acceptPacket(issue(request, issuer, secret, "wrong-label")), "OAEP label mismatch");
        rejected(() -> receiver.acceptPacket(issue(request, issuer, new byte[16], "smart-lock/course/key-wrap/v1")), "wrong key length");
        Map<String, Object> corrupt = D2dCrypto.parseObject(packet);
        byte[] signature = un64(corrupt.get("signature"));
        signature[signature.length - 1] ^= 1;
        corrupt.put("signature", b64(signature));
        rejected(() -> receiver.acceptPacket(D2dCrypto.json(corrupt)), "tampered signature");
        receiver.acceptPacket(packet);
        check(receiver.hasSession(), "valid packet established");
        rejected(() -> receiver.acceptPacket(packet), "duplicate accept");
        Map<String, Object> confirm = D2dCrypto.parseObject(receiver.confirmationJson());
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        mac.update(bytes("smartlock/audio-confirm/v1\0"));
        check(Arrays.equals(mac.doFinal(bytes(D2dCrypto.json(binding(confirm)))), un64(confirm.get("proof"))), "confirmation HMAC");
        String message = "Android → Pi 你好";
        Map<String, Object> sent = D2dCrypto.parseObject(receiver.encryptMessage(message));
        Cipher gcm = Cipher.getInstance("AES/GCM/NoPadding");
        gcm.init(Cipher.DECRYPT_MODE, new SecretKeySpec(secret, "AES"), new GCMParameterSpec(128, un64(sent.get("nonce"))));
        gcm.updateAAD(bytes("smartlock/audio-message/v1\0"));
        gcm.updateAAD(bytes(D2dCrypto.json(binding(sent))));
        check(Arrays.equals(gcm.doFinal(un64(sent.get("ciphertext"))), bytes(message)), "AES-GCM plaintext");
        String second = receiver.encryptMessage(message);
        check(!sent.get("nonce").equals(D2dCrypto.parseObject(second).get("nonce")), "fresh nonce per message");
        rejected(() -> receiver.encryptMessage(""), "empty message");
        rejected(() -> receiver.encryptMessage("x".repeat(1025)), "oversized message");
        now.set(1180);
        check(!receiver.hasSession(), "expiry erases accepted state");
        rejected(receiver::confirmationJson, "expired confirmation");
        now.set(1000);
        receiver.beginRequest("operator", "phone_01", b64(issuer.getPublic().getEncoded()));
        rejected(() -> receiver.acceptPacket(packet), "old packet after lifecycle restart");
        receiver.clear();
        check(receiver.expiresAtEpochSeconds() == 0, "explicit clear");
        rejected(() -> receiver.beginRequest("含中文", "phone", b64(issuer.getPublic().getEncoded())), "non-ASCII identity");
        rejected(() -> receiver.beginRequest("same", "same", b64(issuer.getPublic().getEncoded())), "same identities");
        rejected(() -> receiver.beginRequest("operator", "phone", "AAAA"), "invalid pinned public key");
        KeyPairGenerator wrongCurve = KeyPairGenerator.getInstance("EC");
        wrongCurve.initialize(new ECGenParameterSpec("secp384r1"));
        rejected(() -> receiver.beginRequest("operator", "phone", b64(wrongCurve.generateKeyPair().getPublic().getEncoded())), "wrong issuer curve");
        System.out.println("D2dCrypto JVM checks passed: " + checks);
    }

    private static void python(String executable, Path root, Path state, String... arguments) throws Exception {
        java.util.List<String> command = new java.util.ArrayList<>();
        command.add(executable);
        command.add("-B");
        command.add(root.resolve("deploy/audio_peer.py").toString());
        command.add("--state");
        command.add(state.toString());
        command.addAll(Arrays.asList(arguments));
        Process process = new ProcessBuilder(command).directory(root.toFile()).inheritIO().start();
        if (!process.waitFor(60, java.util.concurrent.TimeUnit.SECONDS)) {
            process.destroyForcibly();
            throw new AssertionError("Python interoperability step timed out");
        }
        if (process.exitValue() != 0) throw new AssertionError("Python interoperability step failed");
    }

    private static void interoperability(String executable, Path root, Path output) throws Exception {
        Files.createDirectories(output);
        Path state = Files.createTempDirectory("smartlock-d2d-test-");
        Path issuer = output.resolve("issuer.der");
        python(executable, root, state, "init-issuer", "--identity", "operator", "--public-output", issuer.toString());
        D2dCrypto receiver = new D2dCrypto();
        Path request = output.resolve("request.json");
        Files.writeString(request, receiver.beginRequest("operator", "phone_01", b64(Files.readAllBytes(issuer))));
        Path publicKey = output.resolve("receiver.der");
        Files.write(publicKey, Base64.getDecoder().decode(receiver.recipientPublicKeyBase64()));
        Path requestWave = output.resolve("request.wav");
        Files.write(requestWave, WaveFile.encode(OfdmCodec.encode(Files.readAllBytes(request))));
        Path packet = output.resolve("packet.wav");
        python(executable, root, state, "issue", "--input", requestWave.toString(), "--receiver-public", publicKey.toString(), "--output", packet.toString());
        receiver.acceptPacket(new String(OfdmCodec.decode(WaveFile.decode(Files.readAllBytes(packet))), StandardCharsets.UTF_8));
        Path confirm = output.resolve("confirm.wav");
        Files.write(confirm, WaveFile.encode(OfdmCodec.encode(bytes(receiver.confirmationJson()))));
        python(executable, root, state, "confirm", "--input", confirm.toString(), "--output", output.resolve("confirm-result.json").toString());
        Path message = output.resolve("message.wav");
        String plaintext = "Android Java → Python Pi: 课程双端互通";
        Files.write(message, WaveFile.encode(OfdmCodec.encode(bytes(receiver.encryptMessage(plaintext)))));
        Path recovered = output.resolve("plaintext.bin");
        python(executable, root, state, "open", "--input", message.toString(), "--output", recovered.toString());
        check(Arrays.equals(Files.readAllBytes(recovered), bytes(plaintext)), "Python recovered Java message");
        receiver.clear();
        Files.writeString(output.resolve("result.json"), "{\"passed\":true,\"transport\":\"cross-language OFDM PCM/WAV (no physical audio)\",\"path\":\"Java request -> Python issue -> Java accept -> Java confirm/message -> Python verify/open\"}\n");
        System.out.println("D2dCrypto Python/Java interoperability passed");
    }

    public static void main(String[] args) throws Exception {
        unitTests();
        if (args.length == 4 && args[0].equals("interop"))
            interoperability(args[1], Path.of(args[2]), Path.of(args[3]));
        else if (args.length != 0) throw new IllegalArgumentException("Use: interop PYTHON REPOSITORY OUTPUT_DIRECTORY");
    }
}
