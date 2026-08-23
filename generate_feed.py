import os
import sys
from xml.sax.saxutils import escape

import requests

SHOP = os.environ.get("SHOPIFY_STORE_DOMAIN", "6f8ca0-2.myshopify.com")
TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
API_VERSION = "2026-01"
STORE_URL = "https://modino.co.il"

if not TOKEN:
    print("ERROR: SHOPIFY_ACCESS_TOKEN is not set", file=sys.stderr)
    sys.exit(1)

QUERY = """
query($cursor: String) {
  products(first: 100, after: $cursor, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        title
        handle
        productType
        featuredImage { url }
        variants(first: 50) {
          edges {
            node {
              sku
              price
              availableForSale
              inventoryQuantity
            }
          }
        }
      }
    }
  }
}
"""


def fetch_all_products():
    products = []
    cursor = None
    while True:
        resp = requests.post(
            f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json",
            json={"query": QUERY, "variables": {"cursor": cursor}},
            headers={
                "X-Shopify-Access-Token": TOKEN,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"Shopify API errors: {data['errors']}")
        block = data["data"]["products"]
        products.extend(block["edges"])
        if block["pageInfo"]["hasNextPage"]:
            cursor = block["pageInfo"]["endCursor"]
        else:
            break
    return products


def build_xml(products):
    items = []
    for edge in products:
        node = edge["node"]
        title = escape(node["title"])
        handle = node["handle"]
        link = escape(f"{STORE_URL}/products/{handle}")
        image = node.get("featuredImage") or {}
        image_link = escape(image.get("url") or "")
        category = escape(node.get("productType") or "")

        for vedge in node["variants"]["edges"]:
            v = vedge["node"]
            sku = escape(v.get("sku") or handle)
            price = v.get("price", "0.00")
            qty = v.get("inventoryQuantity") or 0
            availability = (
                "in stock" if v.get("availableForSale") and qty > 0 else "out of stock"
            )
            items.append(
                f"""    <item>
      <g:id>{sku}</g:id>
      <title>{title}</title>
      <link>{link}</link>
      <g:image_link>{image_link}</g:image_link>
      <g:price>{price} ILS</g:price>
      <g:availability>{availability}</g:availability>
      <g:quantity>{qty}</g:quantity>
      <g:product_type>{category}</g:product_type>
      <g:condition>new</g:condition>
    </item>"""
            )

    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
  <channel>
    <title>Modino Product Feed</title>
    <link>{STORE_URL}</link>
    <description>Live product, price and inventory feed</description>
{body}
  </channel>
</rss>
"""


def main():
    products = fetch_all_products()
    if not products:
        print("ERROR: no products returned, refusing to overwrite existing feed", file=sys.stderr)
        sys.exit(1)
    xml = build_xml(products)
    os.makedirs("docs", exist_ok=True)
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Wrote {len(products)} products to docs/feed.xml")


if __name__ == "__main__":
    main()
