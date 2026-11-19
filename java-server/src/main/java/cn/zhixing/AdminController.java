package cn.zhixing;

import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/admin")
public class AdminController {

    private static final String ROOM_CACHE_KEY = "office:room-catalog:v3";

    private final JdbcTemplate jdbc;
    private final StringRedisTemplate redis;
    private final JwtVerifier verifier;

    public AdminController(JdbcTemplate jdbc, StringRedisTemplate redis, JwtVerifier verifier) {
        this.jdbc = jdbc;
        this.redis = redis;
        this.verifier = verifier;
    }

    private String requireAdmin(HttpServletRequest request) {
        Map<String, Object> claims = verifier.verify(request.getHeader("Authorization"));
        if (claims == null) {
            throw new ApiError(HttpStatus.UNAUTHORIZED, "登录已失效");
        }
        String username = String.valueOf(claims.get("sub"));
        String role = jdbc.query("select role from office_users where username = ?",
                resultSet -> resultSet.next() ? resultSet.getString(1) : null, username);
        if (!"admin".equals(role)) {
            throw new ApiError(HttpStatus.FORBIDDEN, "需要管理员权限");
        }
        return username;
    }

    @GetMapping("/rooms")
    public List<Map<String, Object>> rooms(HttpServletRequest request) {
        requireAdmin(request);
        return jdbc.query("select name, capacity, enabled from office_room_catalog order by name",
                (resultSet, row) -> {
                    Map<String, Object> item = new LinkedHashMap<>();
                    item.put("name", resultSet.getString("name"));
                    item.put("capacity", resultSet.getInt("capacity"));
                    item.put("enabled", resultSet.getInt("enabled") == 1);
                    return item;
                });
    }

    // Serialize with Python business mutations, then synchronously invalidate both cache layers.
    @PutMapping("/rooms/{name}")
    public Map<String, Object> updateRoom(@PathVariable String name,
            @RequestBody Map<String, Object> body, HttpServletRequest request) {
        requireAdmin(request);
        final String roomName = name.trim();
        if (roomName.isEmpty() || roomName.length() > 100) {
            throw new ApiError(HttpStatus.UNPROCESSABLE_ENTITY, "会议室名称为1至100字");
        }
        int capacity;
        try { capacity = Integer.parseInt(String.valueOf(body.get("capacity"))); }
        catch (NumberFormatException e) { throw new ApiError(HttpStatus.UNPROCESSABLE_ENTITY, "容量必须为整数"); }
        if (capacity < 1 || capacity > 1000 || body.keySet().stream().anyMatch(k -> !k.equals("capacity") && !k.equals("enabled"))) {
            throw new ApiError(HttpStatus.UNPROCESSABLE_ENTITY, "目录字段不合法");
        }
        if (body.containsKey("enabled") && !(body.get("enabled") instanceof Boolean)) {
            throw new ApiError(HttpStatus.UNPROCESSABLE_ENTITY, "启用状态必须为布尔值");
        }
        final int size = capacity;
        final boolean enabled = !body.containsKey("enabled") || Boolean.TRUE.equals(body.get("enabled"));
        var transaction = new org.springframework.transaction.support.TransactionTemplate(
                new org.springframework.jdbc.datasource.DataSourceTransactionManager(jdbc.getDataSource()));
        transaction.execute(status -> {
            jdbc.queryForObject("select name from office_resources where name = 'v13:mutation' for update", String.class);
            Integer exists = jdbc.queryForObject("select count(*) from office_room_catalog where name = ?", Integer.class, roomName);
            if (exists != null && exists > 0) {
                jdbc.update("update office_room_catalog set capacity = ?, enabled = ? where name = ?", size, enabled ? 1 : 0, roomName);
            } else {
                jdbc.update("insert into office_room_catalog(name, capacity, enabled) values (?, ?, ?)", roomName, size, enabled ? 1 : 0);
            }
            return null;
        });
        boolean invalidated = false;
        try { redis.delete(ROOM_CACHE_KEY); } catch (Exception ignored) { /* callback marks a dirty key for DB fallback */ }
        try {
            var uri = java.net.URI.create(OfficeConfig.setting("OFFICE_DATA_URL", "http://127.0.0.1:8001") + "/api/v1/admin/cache/invalidate-room");
            var call = java.net.http.HttpRequest.newBuilder(uri).timeout(java.time.Duration.ofSeconds(5))
                .header("Authorization", request.getHeader("Authorization"))
                .POST(java.net.http.HttpRequest.BodyPublishers.noBody()).build();
            var response = java.net.http.HttpClient.newHttpClient().send(call, java.net.http.HttpResponse.BodyHandlers.ofString());
            invalidated = response.statusCode() == 200 && new com.fasterxml.jackson.databind.ObjectMapper()
                .readTree(response.body()).path("cacheInvalidated").asBoolean(false);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (Exception ignored) { /* report DB committed separately from cache status */ }
        return Map.of("updated", true, "cacheInvalidated", invalidated);
    }

    @GetMapping("/summary")
    public Map<String, Object> summary(HttpServletRequest request) {
        requireAdmin(request);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("pendingTotal", count("select count(*) from office_records where kind not in ('chat','schedule') and status = 'pending'"));
        result.put("pendingRoom", count("select count(*) from office_records where kind = 'room' and status = 'pending'"));
        result.put("pendingTravel", count("select count(*) from office_records where kind = 'travel' and status = 'pending'"));
        result.put("pendingVehicle", count("select count(*) from office_records where kind = 'vehicle' and status = 'pending'"));
        result.put("pendingLeave", count("select count(*) from office_records where kind = 'leave' and status = 'pending'"));
        result.put("pendingExpense", count("select count(*) from office_records where kind = 'expense' and status = 'pending'"));
        result.put("records", count("select count(*) from office_records where kind not in ('chat','schedule')"));
        result.put("employees", count("select count(*) from office_users where role = 'employee'"));
        result.put("chats", count("select count(*) from office_records where kind = 'chat'"));
        result.put("roomsEnabled", count("select count(*) from office_room_catalog where enabled = 1"));
        return result;
    }

    private int count(String sql) {
        Integer value = jdbc.queryForObject(sql, Integer.class);
        return value == null ? 0 : value;
    }

    @ExceptionHandler(ApiError.class)
    public ResponseEntity<Map<String, String>> handleApiError(ApiError error) {
        return ResponseEntity.status(error.status).body(Map.of("detail", error.getMessage()));
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<Map<String, String>> handleDatabaseError(DataAccessException error) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of("detail", "数据库暂时不可用"));
    }

    static class ApiError extends RuntimeException {
        private final HttpStatus status;

        ApiError(HttpStatus status, String message) {
            super(message);
            this.status = status;
        }
    }
}
