import os
import sys
from urllib.parse import quote
from xml.sax.saxutils import escape

import requests

SHOP = os.environ.get("SHOPIFY_STORE_DOMAIN", "6f8ca0-2.myshopify.com")
TOKEN = (os.environ.get("SHOPIFY_ACCESS_TOKEN") or "").strip()
API_VERSION = "2026-01"
STORE_URL = "https://modino.co.il"
ISRAEL_VAT_PERCENT = "18"

if not TOKEN:
    print("ERROR: SHOPIFY_ACCESS_TOKEN is not set", file=sys.stderr)
    sys.exit(1)

QUERY = """
query($cursor: String) {
  products(first: 100, after: $cursor, query: "status:active") {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        handle
        description
        vendor
        productType
        featuredImage { url }
        collections(first: 1) { edges { node { id title } } }
        variants(first: 100) {
          edges {
            node {
              id
              sku
              price
              availableForSale
              image { url }
              selectedOptions { name value }
            }
          }
        }
      }
    }
  }
}
"""


def gid_to_numeric(gid):
    """Extract the stable numeric id from a Shopify GID (gid://shopify/X/123) -> '123'."""
    return gid.rsplit("/", 1)[-1]


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


def build_product_xml(**fields):
    return f"""    <PRODUCT>
      <PRODUCT_URL>{fields['product_url']}</PRODUCT_URL>
      <PRODUCT_NAME>{fields['product_name']}</PRODUCT_NAME>
      <MODEL>{fields['model']}</MODEL>
      <DETAILS>{fields['details']}</DETAILS>
      <CATALOG_NUMBER>{fields['catalog_number']}</CATALOG_NUMBER>
      <PRODUCTCODE>{fields['productcode']}</PRODUCTCODE>
      <CURRENCY>{fields['currency']}</CURRENCY>
      <PRICE>{fields['price']}</PRICE>
      <SHIPMENT_COST>{fields['shipment_cost']}</SHIPMENT_COST>
      <DELIVERY_TIME>{fields['delivery_time']}</DELIVERY_TIME>
      <MANUFACTURER>{fields['manufacturer']}</MANUFACTURER>
      <WARRANTY></WARRANTY>
      <IMAGE>{fields['image']}</IMAGE>
      <TAX>{fields['tax']}</TAX>
      <CATEGORY_ID>{fields['category_id']}</CATEGORY_ID>
      <CATEGORY_NAME>{fields['category_name']}</CATEGORY_NAME>
    </PRODUCT>"""


def build_xml(products):
    items = []
    skipped_out_of_stock = 0

    for edge in products:
        node = edge["node"]
        product_id = gid_to_numeric(node["id"])
        title = node["title"]
        handle = node["handle"]
        base_url = f"{STORE_URL}/products/{handle}"
        details = escape((node.get("description") or "")[:500])
        manufacturer = escape(node.get("vendor") or "")

        collection_edges = node.get("collections", {}).get("edges", [])
        if collection_edges:
            category_id = gid_to_numeric(collection_edges[0]["node"]["id"])
            category_name = escape(collection_edges[0]["node"]["title"])
        else:
            category_id = ""
            category_name = escape(node.get("productType") or "")

        variant_edges = node["variants"]["edges"]
        # A "simple" product has exactly one variant with no real options
        # (Shopify gives it a single pseudo-option named "Title" / "Default Title").
        is_simple = len(variant_edges) == 1 and all(
            opt["name"] in ("Title",) for opt in variant_edges[0]["node"]["selectedOptions"]
        )

        for vedge in variant_edges:
            v = vedge["node"]
            if not v.get("availableForSale"):
                skipped_out_of_stock += 1
                continue

            variant_id = gid_to_numeric(v["id"])
            sku = v.get("sku") or f"{handle}-{variant_id}"
            price = v.get("price", "0.00")
            image = (v.get("image") or {}).get("url") or (node.get("featuredImage") or {}).get("url") or ""

            if is_simple:
                product_url = escape(base_url)
                product_name = escape(title)
            else:
                params = []
                readable_bits = []
                for opt in v["selectedOptions"]:
                    attr_name = "attribute_pa_" + opt["name"].strip().lower().replace(" ", "-")
                    value_slug = quote(opt["value"].strip().lower().replace(" ", "-"))
                    params.append(f"{attr_name}={value_slug}")
                    readable_bits.append(opt["value"])
                product_url = escape(base_url + "?" + "&".join(params))
                product_name = escape(f"{title} {' '.join(readable_bits)}")

            items.append(
                build_product_xml(
                    product_url=product_url,
                    product_name=product_name,
                    model=escape(title),
                    details=details,
                    catalog_number=escape(sku),
                    productcode=variant_id,
                    currency="ILS",
                    price=price,
                    shipment_cost="0",
                    delivery_time="5",
                    manufacturer=manufacturer,
                    image=escape(image),
                    tax=ISRAEL_VAT_PERCENT,
                    category_id=category_id,
                    category_name=category_name,
                )
            )

    if skipped_out_of_stock:
        print(f"Skipped {skipped_out_of_stock} out-of-stock variant(s)")

    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<STORE>
  <PRODUCTS>
{body}
  </PRODUCTS>
</STORE>
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
    print(f"Wrote feed with {len(products)} product(s) to docs/feed.xml")


if __name__ == "__main__":
    main()
