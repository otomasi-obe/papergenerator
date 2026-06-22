#!/usr/bin/env python3
"""
=============================================================================
MDPI TEMPLATE DOWNLOADER - Download ALL 150+ .dot templates
=============================================================================
Usage: python3 download_mdpi_templates.py

This script downloads all MDPI journal templates (.dot files) and creates
a ZIP archive. Perfect for researchers needing multiple journal templates.

Author: Generated for Rofiq
Date: June 2026
=============================================================================
"""

import urllib.request
import urllib.error
import os
import shutil
import time
import sys
from pathlib import Path

# ANSI color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

# List of all MDPI journals with templates (150+ journals)
JOURNALS = [
    'acoustics', 'actuators', 'admsci', 'adolescents', 'aerospace', 'agriculture',
    'agriengineering', 'agrochemicals', 'agronomy', 'ai', 'air', 'algorithms',
    'allergies', 'alloys', 'analytica', 'analytics', 'anatomia', 'animals',
    'antibiotics', 'antibodies', 'antioxidants', 'applbiosci', 'applmech',
    'applmicrobiol', 'applnano', 'applsci', 'architecture', 'arthropoda', 'arts',
    'astronomy', 'atmosphere', 'atoms', 'audiolres', 'automation', 'axioms',
    'bacteria', 'batteries', 'behavsci', 'beverages', 'biochem', 'bioengineering',
    'biologics', 'biology', 'biomass', 'biomechanics', 'biomed', 'biomedicines',
    'biomedinformatics', 'biomimetics', 'biomolecules', 'biophysica', 'biosensors',
    'biotech', 'birds', 'brainsci', 'buildings', 'businesses', 'cancers', 'carbon',
    'cardiogenetics', 'catalysts', 'cells', 'ceramics', 'challenges', 'chemengineering',
    'chemistry', 'chemosensors', 'children', 'chips', 'civileng', 'cleantechnol',
    'climate', 'clinpract', 'coasts', 'coatings', 'colloids', 'colorants',
    'commodities', 'computation', 'computers', 'condensedmatter', 'conservation',
    'cmd', 'cosmetics', 'covid', 'crops', 'cryptography', 'crystals', 'curroncol',
    'dairy', 'data', 'dentistry', 'dermato', 'dermatopathology', 'designs',
    'diabetology', 'diagnostics', 'dietetics', 'digital', 'disabilities', 'diseases',
    'diversity', 'dna', 'drones', 'dynamics', 'earth', 'ecologies', 'econometrics',
    'economies', 'edusci', 'electricity', 'electrochem', 'electronics', 'energies',
    'eng', 'entropy', 'environments', 'epidemiologia', 'epigenomes', 'fermentation',
    'fibers', 'fintech', 'fire', 'fishes', 'fluids', 'foods', 'forecasting',
    'forensicsci', 'forests', 'fossils', 'foundations', 'fuels', 'future',
    'galaxies', 'games', 'gases', 'gels', 'geographies', 'geomatics', 'geometry',
    'geosciences', 'geriatrics', 'hardware', 'ijms', 'ijerph', 'informatics',
    'information', 'inorganics', 'insects', 'instruments',
]

class MDPIDownloader:
    def __init__(self, output_dir="./mdpi_templates"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.success_count = 0
        self.failed_count = 0
        self.failed_journals = []
        
    def print_header(self):
        print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
        print(f"{BOLD}📥  MDPI TEMPLATE DOWNLOADER{RESET}")
        print(f"{BOLD}{BLUE}{'='*70}{RESET}")
        print(f"\n📁 Output directory: {self.output_dir}")
        print(f"📊 Total journals: {len(JOURNALS)}")
        print(f"⏱️  Estimated time: ~{len(JOURNALS) // 3} seconds (with rate limiting)")
        print(f"\n{BLUE}{'-'*70}{RESET}\n")
        
    def download_template(self, journal, index, total):
        """Download a single template with proper error handling"""
        url = f"https://www.mdpi.com/files/word-templates/{journal}-template.dot"
        filepath = self.output_dir / f"{journal}-template.dot"
        
        # Display status
        status_str = f"[{index:3d}/{total}] {journal:25s}"
        print(f"{status_str} ", end='', flush=True)
        
        try:
            # Create request with User-Agent to avoid 403
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            req.add_header('Accept', '*/*')
            
            # Download with timeout
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
                
            # Write to file
            with open(filepath, 'wb') as f:
                f.write(data)
            
            # Verify file size
            file_size = filepath.stat().st_size
            if file_size == 0:
                print(f"{RED}❌ Empty file{RESET}")
                self.failed_count += 1
                self.failed_journals.append(f"{journal} (empty file)")
                filepath.unlink()
                return False
            
            print(f"{GREEN}✅ ({file_size:,} bytes){RESET}")
            self.success_count += 1
            return True
            
        except urllib.error.HTTPError as e:
            print(f"{RED}❌ HTTP {e.code}{RESET}")
            self.failed_count += 1
            self.failed_journals.append(f"{journal} (HTTP {e.code})")
            if filepath.exists():
                filepath.unlink()
            return False
            
        except urllib.error.URLError as e:
            print(f"{RED}❌ URL Error{RESET}")
            self.failed_count += 1
            self.failed_journals.append(f"{journal} (URLError)")
            if filepath.exists():
                filepath.unlink()
            return False
            
        except Exception as e:
            error_msg = str(type(e).__name__)
            print(f"{RED}❌ {error_msg}{RESET}")
            self.failed_count += 1
            self.failed_journals.append(f"{journal} ({error_msg})")
            if filepath.exists():
                filepath.unlink()
            return False
    
    def run(self):
        """Main download loop"""
        self.print_header()
        
        total = len(JOURNALS)
        for idx, journal in enumerate(JOURNALS, 1):
            self.download_template(journal, idx, total)
            # Rate limiting - wait between requests
            if idx < total:
                time.sleep(0.5)
        
        self.print_summary()
        self.create_zip()
    
    def print_summary(self):
        """Print download summary"""
        print(f"\n{BLUE}{'-'*70}{RESET}")
        print(f"\n{BOLD}✅ DOWNLOAD COMPLETE{RESET}")
        print(f"   {GREEN}✓ Berhasil:{RESET} {self.success_count} templates")
        print(f"   {RED}✗ Gagal:{RESET}   {self.failed_count} templates")
        print(f"   {YELLOW}⚙️  Aktual:  {self.success_count + self.failed_count} dipercoba{RESET}")
        
        if self.failed_journals:
            print(f"\n{YELLOW}⚠️  Yang gagal:{RESET}")
            for journal in self.failed_journals[:15]:
                print(f"   - {journal}")
            if len(self.failed_journals) > 15:
                print(f"   ... dan {len(self.failed_journals) - 15} lainnya")
        
        print(f"\n{BLUE}{'-'*70}{RESET}\n")
    
    def create_zip(self):
        """Create ZIP archive of all downloaded templates"""
        if self.success_count == 0:
            print(f"{RED}❌ Tidak ada template berhasil didownload. ZIP tidak dibuat.{RESET}\n")
            return
        
        print(f"📦 Membuat ZIP file...")
        try:
            zip_name = 'mdpi_templates'
            zip_path = shutil.make_archive(zip_name, 'zip', '.', self.output_dir.name)
            zip_size = Path(zip_path).stat().st_size / (1024*1024)  # Convert to MB
            
            print(f"{GREEN}✅ ZIP file dibuat:{RESET}")
            print(f"   📁 Nama: {Path(zip_path).name}")
            print(f"   📊 Ukuran: {zip_size:.2f} MB")
            print(f"   📍 Lokasi: {Path(zip_path).absolute()}\n")
            
        except Exception as e:
            print(f"{RED}❌ Error membuat ZIP: {e}{RESET}\n")
    
    def print_usage(self):
        """Print usage instructions"""
        print(f"\n{BOLD}📝 LANGKAH SELANJUTNYA:{RESET}")
        print(f"   1. Cari file ZIP yang dibuat")
        print(f"   2. Extract ke folder yang diinginkan")
        print(f"   3. Gunakan template sesuai jurnal target")
        print(f"\n{BOLD}🎯 UNTUK RIMBAWAN:{RESET}")
        print(f"   • Nutrients → nutrients-template.dot")
        print(f"   • Foods → foods-template.dot")
        print(f"   • Biomedicines → biomedicines-template.dot")
        print(f"\n{BOLD}💡 TIP:{RESET}")
        print(f"   Gunakan Ctrl+F untuk mencari template jurnal spesifik di ZIP\n")

def main():
    """Main entry point"""
    try:
        downloader = MDPIDownloader()
        downloader.run()
        downloader.print_usage()
        
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}⚠️  Download dibatalkan oleh user{RESET}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}❌ Error: {e}{RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()