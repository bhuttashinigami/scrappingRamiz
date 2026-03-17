#!/bin/bash
# ═══════════════════════════════════════════════════════
#  Fix: Missing Playwright system libraries
#  Run this: bash fix_playwright.sh
# ═══════════════════════════════════════════════════════

echo ""
echo "🔧 Installing missing Playwright system dependencies..."
echo "═══════════════════════════════════════════════════════"

# Install all required system libraries for Chromium
sudo apt-get update -qq

sudo apt-get install -y \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2 \
  libpango-1.0-0 \
  libcairo2 \
  libnspr4 \
  libnss3 \
  libatspi2.0-0 \
  libwayland-client0 \
  --no-install-recommends -qq

echo ""
echo "✅ System libraries installed!"

# Re-install Playwright browsers cleanly
echo ""
echo "🌐 Re-installing Playwright Chromium..."
playwright install chromium
playwright install-deps chromium

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ All done! Now run:"
echo "  python scrape_ramizac.py"
echo "═══════════════════════════════════════════════════════"
echo ""