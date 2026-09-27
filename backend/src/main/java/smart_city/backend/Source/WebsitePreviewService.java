package smart_city.backend.Source;

import java.io.IOException;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.awt.image.BufferedImage;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import javax.imageio.ImageIO;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.rendering.ImageType;
import org.apache.pdfbox.rendering.PDFRenderer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class WebsitePreviewService {
    private static final Duration CACHE_TTL = Duration.ofMinutes(10);
    private static final int MAX_CACHE_ENTRIES = 32;
    private static final int MAX_REDIRECTS = 5;
    private static final int MAX_PDF_BYTES = 50 * 1024 * 1024;
    private static final String USER_AGENT = "Mozilla/5.0 (compatible; MunicipalSourcePreview/1.0)";

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(4))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    private final String configuredBrowserPath;
    private final Map<String, CacheEntry<Boolean>> embedCache = lruCache(128);
    private final Map<String, CacheEntry<byte[]>> screenshotCache = lruCache(MAX_CACHE_ENTRIES);

    public WebsitePreviewService(@Value("${SCREENSHOT_BROWSER_PATH:}") String configuredBrowserPath) {
        this.configuredBrowserPath = configuredBrowserPath == null ? "" : configuredBrowserPath.trim();
    }

    public boolean canEmbed(String value, String sourceKind) {
        String key = cacheKey(value, sourceKind);
        CacheEntry<Boolean> cached = cached(embedCache, key);
        if (cached != null) return cached.value();
        boolean result = probeEmbeddable(value, sourceKind);
        put(embedCache, key, result);
        return result;
    }

    public byte[] capture(String value, String sourceKind) {
        URI uri = publicHttpUri(value);
        String key = cacheKey(uri.toString(), sourceKind);
        CacheEntry<byte[]> cached = cached(screenshotCache, key);
        if (cached != null) return cached.value().clone();

        if (looksLikePdf(uri, sourceKind) || remoteLooksLikePdf(uri, sourceKind)) {
            try {
                byte[] rendered = renderPdf(downloadPdf(uri));
                put(screenshotCache, key, rendered.clone());
                return rendered;
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                        "PDF screenshot was interrupted", error);
            } catch (IOException error) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                        "PDF screenshot is unavailable", error);
            }
        }

        Path browser = findBrowser().orElseThrow(() -> new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Website screenshots require Chrome or Chromium; configure SCREENSHOT_BROWSER_PATH"));
        Path work = null;
        try {
            work = Files.createTempDirectory("municipal-source-shot-");
            Path image = work.resolve("preview.png");
            Path log = work.resolve("browser.log");
            List<String> command = new ArrayList<>(List.of(
                    browser.toString(),
                    "--headless=new",
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--allow-file-access-from-files",
                    "--run-all-compositor-stages-before-draw",
                    "--window-size=1440,1800",
                    "--virtual-time-budget=10000",
                    "--user-data-dir=" + work.resolve("profile"),
                    "--screenshot=" + image,
                    uri.toString()
            ));
            Process process = new ProcessBuilder(command)
                    .redirectErrorStream(true)
                    .redirectOutput(log.toFile())
                    .start();
            if (!process.waitFor(25, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                throw new ResponseStatusException(HttpStatus.GATEWAY_TIMEOUT,
                        "Website screenshot timed out");
            }
            if (process.exitValue() != 0 || !waitForImage(image, Duration.ofSeconds(5))) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                        "Website screenshot could not be created");
            }
            byte[] bytes = Files.readAllBytes(image);
            if (bytes.length == 0) throw new IOException("Chrome created an empty screenshot");
            put(screenshotCache, key, bytes.clone());
            return bytes;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Website screenshot was interrupted", error);
        } catch (IOException error) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Website screenshot is unavailable", error);
        } finally {
            deleteTree(work);
        }
    }

    private boolean probeEmbeddable(String value, String sourceKind) {
        try {
            URI uri = publicHttpUri(value);
            for (int redirects = 0; redirects <= MAX_REDIRECTS; redirects++) {
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(7))
                        .header("User-Agent", USER_AGENT)
                        .method("HEAD", HttpRequest.BodyPublishers.noBody())
                        .build();
                HttpResponse<Void> response = httpClient.send(request, HttpResponse.BodyHandlers.discarding());
                if (response.statusCode() == 405 || response.statusCode() == 501) {
                    request = HttpRequest.newBuilder(uri)
                            .timeout(Duration.ofSeconds(7))
                            .header("User-Agent", USER_AGENT)
                            .header("Range", "bytes=0-0")
                            .GET()
                            .build();
                    response = httpClient.send(request, HttpResponse.BodyHandlers.discarding());
                }
                if (response.statusCode() >= 300 && response.statusCode() < 400) {
                    String location = response.headers().firstValue("location").orElse("");
                    if (location.isBlank() || redirects == MAX_REDIRECTS) return false;
                    uri = publicHttpUri(uri.resolve(location).toString());
                    continue;
                }
                if (response.statusCode() >= 400) return false;
                String contentType = response.headers().firstValue("content-type")
                        .orElse("").toLowerCase(Locale.ROOT);
                String disposition = response.headers().firstValue("content-disposition")
                        .orElse("").toLowerCase(Locale.ROOT);
                boolean pdf = looksLikePdf(uri, sourceKind, contentType, disposition);
                if (pdf && disposition.contains("attachment")) return false;
                if (!pdf && !contentType.isBlank() && !contentType.contains("text/html")
                        && !contentType.contains("application/xhtml+xml")
                        && !contentType.contains("text/plain")) return false;
                String frameOptions = response.headers().firstValue("x-frame-options")
                        .orElse("").toLowerCase(Locale.ROOT);
                if (frameOptions.contains("deny") || frameOptions.contains("sameorigin")) return false;
                for (String policy : response.headers().allValues("content-security-policy")) {
                    String frameAncestors = directive(policy, "frame-ancestors");
                    if (frameAncestors != null && !frameAncestors.contains("*")) return false;
                }
                return true;
            }
        } catch (IllegalArgumentException | IOException error) {
            return false;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return false;
        }
        return false;
    }

    public Optional<byte[]> inlinePdf(String value, String sourceKind) {
        URI uri = publicHttpUri(value);
        if (!looksLikePdf(uri, sourceKind) && !remoteLooksLikePdf(uri, sourceKind)) {
            return Optional.empty();
        }
        try {
            return Optional.of(downloadPdf(uri));
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "PDF download was interrupted", error);
        } catch (IOException error) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "PDF download is unavailable", error);
        }
    }

    private boolean remoteLooksLikePdf(URI initialUri, String sourceKind) {
        URI uri = initialUri;
        try {
            for (int redirects = 0; redirects <= MAX_REDIRECTS; redirects++) {
                HttpRequest request = HttpRequest.newBuilder(uri)
                        .timeout(Duration.ofSeconds(7))
                        .header("User-Agent", USER_AGENT)
                        .method("HEAD", HttpRequest.BodyPublishers.noBody())
                        .build();
                HttpResponse<Void> response = httpClient.send(request, HttpResponse.BodyHandlers.discarding());
                if (response.statusCode() >= 300 && response.statusCode() < 400) {
                    String location = response.headers().firstValue("location").orElse("");
                    if (location.isBlank() || redirects == MAX_REDIRECTS) return false;
                    uri = publicHttpUri(uri.resolve(location).toString());
                    continue;
                }
                if (response.statusCode() >= 400) return false;
                return looksLikePdf(uri, sourceKind,
                        response.headers().firstValue("content-type").orElse(""),
                        response.headers().firstValue("content-disposition").orElse(""));
            }
        } catch (IllegalArgumentException | IOException error) {
            return false;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return false;
        }
        return false;
    }

    private byte[] downloadPdf(URI initialUri) throws IOException, InterruptedException {
        URI uri = initialUri;
        for (int redirects = 0; redirects <= MAX_REDIRECTS; redirects++) {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(15))
                    .header("User-Agent", USER_AGENT)
                    .header("Accept", "application/pdf")
                    .GET()
                    .build();
            HttpResponse<InputStream> response = httpClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                if (response.statusCode() >= 300 && response.statusCode() < 400) {
                    String location = response.headers().firstValue("location").orElse("");
                    if (location.isBlank() || redirects == MAX_REDIRECTS) {
                        throw new IOException("PDF redirect could not be followed");
                    }
                    uri = publicHttpUri(uri.resolve(location).toString());
                    continue;
                }
                if (response.statusCode() >= 400) {
                    throw new IOException("PDF request failed with status " + response.statusCode());
                }
                byte[] bytes = body.readNBytes(MAX_PDF_BYTES + 1);
                if (bytes.length > MAX_PDF_BYTES) throw new IOException("PDF exceeds the 50 MB preview limit");
                if (bytes.length < 5 || bytes[0] != '%' || bytes[1] != 'P' || bytes[2] != 'D'
                        || bytes[3] != 'F' || bytes[4] != '-') {
                    throw new IOException("Source did not return a PDF document");
                }
                return bytes;
            }
        }
        throw new IOException("Too many PDF redirects");
    }

    static byte[] renderPdf(byte[] bytes) throws IOException {
        try (PDDocument document = Loader.loadPDF(bytes)) {
            if (document.getNumberOfPages() == 0) throw new IOException("PDF has no pages");
            PDRectangle box = document.getPage(0).getCropBox();
            float width = Math.max(1, box.getWidth());
            float height = Math.max(1, box.getHeight());
            float scale = Math.max(0.1f, Math.min(2f, Math.min(1440f / width, 1800f / height)));
            BufferedImage image = new PDFRenderer(document).renderImage(0, scale, ImageType.RGB);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            if (!ImageIO.write(image, "png", output)) throw new IOException("PNG encoder is unavailable");
            return output.toByteArray();
        }
    }

    static boolean looksLikePdf(URI uri, String sourceKind) {
        return looksLikePdf(uri, sourceKind, "", "");
    }

    static boolean looksLikePdf(URI uri, String sourceKind, String contentType, String contentDisposition) {
        if (sourceKind != null && sourceKind.equalsIgnoreCase("pdf")) return true;
        String path = uri.getPath();
        if (path != null && path.toLowerCase(Locale.ROOT).endsWith(".pdf")) return true;
        String type = contentType == null ? "" : contentType.toLowerCase(Locale.ROOT);
        if (type.contains("application/pdf")) return true;
        String disposition = contentDisposition == null ? "" : contentDisposition.toLowerCase(Locale.ROOT);
        return disposition.matches("(?s).*filename\\*?\\s*=.*\\.pdf(?:[\\\"';\\s]|$).*");
    }

    private static String cacheKey(String value, String sourceKind) {
        return (sourceKind == null ? "" : sourceKind.toLowerCase(Locale.ROOT)) + ":" + value;
    }

    private static String directive(String policy, String name) {
        for (String item : policy.toLowerCase(Locale.ROOT).split(";")) {
            String trimmed = item.trim();
            if (trimmed.equals(name) || trimmed.startsWith(name + " ")) return trimmed;
        }
        return null;
    }

    private static boolean waitForImage(Path image, Duration timeout) throws InterruptedException, IOException {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline)) {
            if (Files.isRegularFile(image) && Files.size(image) > 0) return true;
            Thread.sleep(100);
        }
        return Files.isRegularFile(image) && Files.size(image) > 0;
    }

    static URI publicHttpUri(String value) {
        try {
            URI uri = URI.create(value == null ? "" : value.trim());
            if (!("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))
                    || uri.getHost() == null || uri.getUserInfo() != null) {
                throw new IllegalArgumentException("Only public HTTP(S) source URLs can be captured");
            }
            for (InetAddress address : InetAddress.getAllByName(uri.getHost())) {
                if (!isPublic(address)) throw new IllegalArgumentException("Private source URLs cannot be captured");
            }
            return uri;
        } catch (IOException error) {
            throw new IllegalArgumentException("Source hostname could not be resolved", error);
        }
    }

    private static boolean isPublic(InetAddress address) {
        if (address.isAnyLocalAddress() || address.isLoopbackAddress() || address.isLinkLocalAddress()
                || address.isSiteLocalAddress() || address.isMulticastAddress()) return false;
        byte[] bytes = address.getAddress();
        if (address instanceof Inet6Address) {
            int first = Byte.toUnsignedInt(bytes[0]);
            return (first & 0xfe) != 0xfc;
        }
        int first = Byte.toUnsignedInt(bytes[0]);
        int second = Byte.toUnsignedInt(bytes[1]);
        return !(first == 0 || first == 100 && second >= 64 && second <= 127
                || first == 127 || first >= 224);
    }

    private Optional<Path> findBrowser() {
        if (!configuredBrowserPath.isBlank()) {
            Path configured = Path.of(configuredBrowserPath);
            return Files.isRegularFile(configured) ? Optional.of(configured) : Optional.empty();
        }
        List<String> candidates = System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win")
                ? List.of(
                    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
                    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe")
                : List.of("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
                    "/usr/bin/chromium", "/usr/bin/chromium-browser");
        return candidates.stream().map(Path::of).filter(Files::isRegularFile).findFirst();
    }

    private static <T> Map<String, CacheEntry<T>> lruCache(int capacity) {
        return new LinkedHashMap<>(capacity, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, CacheEntry<T>> eldest) {
                return size() > capacity;
            }
        };
    }

    private static synchronized <T> CacheEntry<T> cached(Map<String, CacheEntry<T>> cache, String key) {
        CacheEntry<T> entry = cache.get(key);
        if (entry != null && entry.createdAt().plus(CACHE_TTL).isAfter(Instant.now())) return entry;
        if (entry != null) cache.remove(key);
        return null;
    }

    private static synchronized <T> void put(Map<String, CacheEntry<T>> cache, String key, T value) {
        cache.put(key, new CacheEntry<>(value, Instant.now()));
    }

    private static void deleteTree(Path root) {
        if (root == null) return;
        try (var paths = Files.walk(root)) {
            paths.sorted((left, right) -> right.compareTo(left)).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (IOException ignored) { }
            });
        } catch (IOException ignored) { }
    }

    private record CacheEntry<T>(T value, Instant createdAt) { }
}
