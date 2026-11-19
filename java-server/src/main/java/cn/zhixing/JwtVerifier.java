package cn.zhixing;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class JwtVerifier {

    private final byte[] secret;
    private final ObjectMapper mapper = new ObjectMapper();

    public JwtVerifier(String secret) {
        this.secret = secret == null ? new byte[0] : secret.getBytes(StandardCharsets.UTF_8);
    }

    public boolean isConfigured() {
        return secret.length > 0;
    }

    public Map<String, Object> verify(String authorizationHeader) {
        if (secret.length == 0 || authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            return null;
        }
        String token = authorizationHeader.substring(7).trim();
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            return null;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal((parts[0] + "." + parts[1]).getBytes(StandardCharsets.UTF_8));
            byte[] actual = Base64.getUrlDecoder().decode(parts[2]);
            if (!MessageDigest.isEqual(expected, actual)) {
                return null;
            }
            Map<String, Object> payload = mapper.readValue(
                    Base64.getUrlDecoder().decode(parts[1]), new TypeReference<Map<String, Object>>() { });
            Object expiration = payload.get("exp");
            if (!(expiration instanceof Number) || ((Number) expiration).longValue() < Instant.now().getEpochSecond()) {
                return null;
            }
            Object subject = payload.get("sub");
            if (subject == null || String.valueOf(subject).isBlank()) {
                return null;
            }
            return payload;
        } catch (Exception exception) {
            return null;
        }
    }
}
