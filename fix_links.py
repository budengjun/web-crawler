import sqlite3
import yaml
from urllib.parse import urljoin
import os

DB_PATH = "jobs.db"
CONFIG_PATH = "config.yaml"

def fix_links():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    company_urls = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                config = yaml.safe_load(f)
            for target in config.get("targets", []):
                name = str(target.get("name", "")).strip()
                url = target.get("url", "")
                if name and url:
                    company_urls[name] = url
                    # Also store lowercase for easier matching
                    company_urls[name.lower()] = url
        except Exception as e:
            print(f"⚠️ Could not fully parse config: {e}")

    # Standard fallbacks for known platforms if config fails
    fallbacks = {
        "NVIDIA": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        "Sanctuary AI": "https://sanctuary.ai/careers/",
        "Layer 6 AI": "https://layer6.ai/careers/",
        "Visier": "https://visier.wd1.myworkdayjobs.com/Visier_External",
        "Indeed": "https://ca.indeed.com",
        "LinkedIn": "https://www.linkedin.com"
    }
    for k, v in fallbacks.items():
        if k not in company_urls:
            company_urls[k] = v
            company_urls[k.lower()] = v

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Find jobs where apply_link starts with /
    cursor.execute("SELECT rowid, title, company, apply_link FROM jobs WHERE apply_link LIKE '/%'")
    broken_jobs = cursor.fetchall()
    
    if not broken_jobs:
        print("✅ No broken relative links found in database.")
        conn.close()
        return

    print(f"🔍 Found {len(broken_jobs)} jobs with relative apply links. Attempting to fix...")
    
    fixed_count = 0
    for rowid, title, company, link in broken_jobs:
        comp_lookup = str(company).strip()
        base_url = company_urls.get(comp_lookup) or company_urls.get(comp_lookup.lower())
        
        # Heuristic: if company is "NVIDIA", ensure we use their workday base
        if "NVIDIA" in comp_lookup:
            base_url = fallbacks["NVIDIA"]

        if base_url:
            # For Workday, urljoin can be tricky if the base doesn't end in / or we are joining a path
            # Standard urljoin(/job, https://site/site) -> https://site/job
            # We want https://site/site/job? No, usually workday links are relative to host.
            from urllib.parse import urlparse
            p = urlparse(base_url)
            host_base = f"{p.scheme}://{p.netloc}"
            
            new_link = urljoin(host_base, link)
            cursor.execute("UPDATE jobs SET apply_link = ? WHERE rowid = ?", (new_link, rowid))
            fixed_count += 1
            print(f"  [FIXED] {company}: {title[:40]}... -> {new_link[:50]}...")
        else:
            print(f"  [SKIPPED] Could not find base URL for company: '{company}'")

    conn.commit()
    conn.close()
    print(f"\n✨ Done! Fixed {fixed_count} links.")

if __name__ == "__main__":
    fix_links()
