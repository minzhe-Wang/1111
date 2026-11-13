package cn.zhixing;

import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class ApiController {
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    private final String upstream = System.getenv().getOrDefault("OFFICE_DATA_URL", "http://127.0.0.1:8001");

    @RequestMapping("/api/v1/**")
    public ResponseEntity<byte[]> forward(HttpServletRequest request, @RequestBody(required=false) byte[] body) {
        try {
            String query = request.getQueryString();
            URI uri = URI.create(upstream + request.getRequestURI() + (query == null ? "" : "?" + query));
            HttpRequest.Builder builder = HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(35));
            for (String header : new String[]{"Authorization", "Content-Type"}) {
                String value = request.getHeader(header);
                if (value != null) builder.header(header, value);
            }
            builder.method(request.getMethod(), body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofByteArray(body));
            HttpResponse<byte[]> response = client.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
            return ResponseEntity.status(response.statusCode())
                .header("Content-Type", response.headers().firstValue("content-type").orElse("application/json"))
                .body(response.body());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(503).build();
        } catch (Exception exception) {
            return ResponseEntity.status(503).header("Content-Type", "application/json")
                .body("{\"detail\":\"数据服务暂时不可用\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        }
    }
}
