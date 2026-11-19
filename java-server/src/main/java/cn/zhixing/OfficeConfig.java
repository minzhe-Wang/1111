package cn.zhixing;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.sql.DataSource;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class OfficeConfig {

    private static final Map<String, String> FILE_ENV = loadEnvFile();

    static String setting(String key, String fallback) {
        String value = System.getenv(key);
        if (value != null && !value.isBlank()) {
            return value;
        }
        return FILE_ENV.getOrDefault(key, fallback);
    }

    private static Map<String, String> loadEnvFile() {
        Map<String, String> values = new HashMap<>();
        List<Path> candidates = List.of(Paths.get(".env"), Paths.get("..", ".env"), Paths.get("..", "..", ".env"));
        for (Path path : candidates) {
            if (!Files.isRegularFile(path)) {
                continue;
            }
            try {
                for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
                    String text = line.trim();
                    if (text.isEmpty() || text.startsWith("#") || !text.contains("=")) {
                        continue;
                    }
                    int index = text.indexOf('=');
                    String key = text.substring(0, index).trim();
                    String value = text.substring(index + 1).trim();
                    if (value.length() >= 2 && value.startsWith("\"") && value.endsWith("\"")) {
                        value = value.substring(1, value.length() - 1);
                    }
                    values.putIfAbsent(key, value);
                }
                break;
            } catch (IOException ignored) {
                // 配置文件不可读时回落到环境变量与默认值
            }
        }
        return values;
    }

    private static String[] parseDatabaseUrl(String url) {
        Matcher matcher = Pattern.compile("^[A-Za-z0-9+]+://([^:]+):([^@]*)@([^/:]+):(\\d+)/([^?]+)").matcher(url);
        if (!matcher.find()) {
            throw new IllegalStateException("DATABASE_URL 格式不支持，应为 mysql+pymysql://用户:密码@主机:端口/库名");
        }
        String user = URLDecoder.decode(matcher.group(1), StandardCharsets.UTF_8);
        String password = URLDecoder.decode(matcher.group(2), StandardCharsets.UTF_8);
        String jdbcUrl = "jdbc:mariadb://" + matcher.group(3) + ":" + matcher.group(4) + "/" + matcher.group(5);
        return new String[]{jdbcUrl, user, password};
    }

    @Bean
    public DataSource dataSource() {
        String[] parts = parseDatabaseUrl(setting("DATABASE_URL",
                "mysql+pymysql://office:office@127.0.0.1:3307/office"));
        return DataSourceBuilder.create()
                .driverClassName("org.mariadb.jdbc.Driver")
                .url(parts[0])
                .username(parts[1])
                .password(parts[2])
                .build();
    }

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        String url = setting("REDIS_URL", "redis://127.0.0.1:6379/0");
        String host = "127.0.0.1";
        int port = 6379;
        int database = 0;
        try {
            java.net.URI uri = java.net.URI.create(url);
            if (uri.getHost() != null) {
                host = uri.getHost();
            }
            if (uri.getPort() > 0) {
                port = uri.getPort();
            }
            String path = uri.getPath();
            if (path != null && path.length() > 1) {
                database = Integer.parseInt(path.substring(1));
            }
        } catch (Exception ignored) {
            // 使用默认本地实例
        }
        RedisStandaloneConfiguration configuration = new RedisStandaloneConfiguration(host, port);
        configuration.setDatabase(database);
        String userInfo = java.net.URI.create(url).getUserInfo();
        if (userInfo != null && userInfo.contains(":")) {
            configuration.setPassword(userInfo.substring(userInfo.indexOf(':') + 1));
        }
        return new LettuceConnectionFactory(configuration);
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(LettuceConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }

    @Bean
    public JwtVerifier jwtVerifier() {
        return new JwtVerifier(setting("JWT_SECRET", ""));
    }
}
