import freemarker.template.Configuration;
import freemarker.template.TemplateDirectiveModel;
import freemarker.template.TemplateExceptionHandler;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

/** Real FreeMarker engine; only the documented YouTrack data adapters are stubbed. */
public class RenderTemplate {
    public static void main(String[] args) throws Exception {
        Properties fixture = new Properties();
        try (Reader reader = Files.newBufferedReader(Path.of(args[2]), StandardCharsets.UTF_8)) {
            fixture.load(reader);
        }
        Map<String, Object> issue = new HashMap<>();
        for (String field : List.of("id", "summary", "description")) {
            String key = "issue." + field;
            if (fixture.containsKey(key)) {
                String kind = fixture.getProperty(key + ".kind", "string");
                Object value = fixture.getProperty(key);
                if (kind.equals("number")) value = 42;
                if (kind.equals("boolean")) value = true;
                if (kind.equals("list")) value = List.of("synthetic");
                if (kind.equals("null")) value = null;
                issue.put(field, value);
            }
        }
        Map<String, Object> model = new HashMap<>();
        model.put("issue", issue);
        model.put("threadSubject", fixture.getProperty("threadSubject", "Synthetic request"));
        model.put("confirmationURL", fixture.getProperty("confirmationURL", "https://example.invalid/ticket?test=1&view=welcome"));
        model.put("commentFromReply", Boolean.parseBoolean(fixture.getProperty("commentFromReply", "false")));
        model.put("l10n", (TemplateDirectiveModel) (env, params, loopVars, body) -> {
            if (body != null) body.render(env.getOut());
        });
        Configuration cfg = new Configuration(Configuration.VERSION_2_3_34);
        cfg.setDefaultEncoding("UTF-8");
        cfg.setTemplateExceptionHandler(TemplateExceptionHandler.RETHROW_HANDLER);
        cfg.setLogTemplateExceptions(false);
        cfg.setWrapUncheckedExceptions(true);
        cfg.setFallbackOnNullLoopVariable(false);
        cfg.setDirectoryForTemplateLoading(Path.of(args[0]).toFile());
        try (Writer writer = Files.newBufferedWriter(Path.of(args[3]), StandardCharsets.UTF_8)) {
            cfg.getTemplate(args[1]).process(model, writer);
        }
    }
}
