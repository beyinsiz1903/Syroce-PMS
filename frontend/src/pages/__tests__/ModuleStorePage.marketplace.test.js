import fs from "fs";
import path from "path";

const source = fs.readFileSync(
  path.join(process.cwd(), "src/pages/ModuleStorePage.jsx"),
  "utf8",
);

describe("professional module marketplace", () => {
  test("uses working purchase, trial and quote actions", () => {
    expect(source).toContain('axios.post("/module-store/purchase"');
    expect(source).toContain('axios.post("/module-store/start-trial"');
    expect(source).toContain('axios.post("/module-store/request-quote"');
    expect(source).toContain("paymentReady ? onPurchase(product, quantity) : onQuote(product)");
    expect(source).toContain('axios.get("/module-store/billing")');
    expect(source).toContain('/cancel`');
  });

  test("supports localized catalog content without Turkish feature leakage", () => {
    expect(source).toContain("product.features_en || []");
    expect(source).toContain("product.name_en");
    expect(source).toContain("product.description_en");
  });

  test("provides search and category filters", () => {
    expect(source).toContain('aria-label={copy(english, "Modül ara", "Search modules")}');
    expect(source).toContain("setCategory(key)");
  });
});
