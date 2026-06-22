#!/usr/bin/env python3
"""Autodocx - Deep analysis & comparison of MDPI .dot templates."""

import json
import hashlib
import zipfile
import io
import os
import re
from pathlib import Path
from collections import Counter, defaultdict
from xml.etree import ElementTree as ET

import docx
from PIL import Image

TEMPLATES_DIR = Path("/home/sirobo/papergenerator/backend/tools/Journal/mdpi_templates")

def get_namespaces(xml_str):
    """Extract namespaces from XML."""
    ns = {}
    for match in re.finditer(r'xmlns:?(.*?)="([^"]+)"', xml_str):
        prefix, uri = match.groups()
        ns[prefix if prefix else ''] = uri
    return ns

def extract_image_hashes(docx_path):
    """Extract images from a .dot file, return {filename: hash}."""
    images = {}
    try:
        with zipfile.ZipFile(docx_path) as zf:
            for name in zf.namelist():
                if name.startswith('word/media/'):
                    img_data = zf.read(name)
                    images[name] = hashlib.md5(img_data).hexdigest()
    except Exception as e:
        images['ERROR'] = str(e)
    return images

def extract_xml_parts(docx_path):
    """Extract key XML parts from .dot."""
    parts = {}
    try:
        with zipfile.ZipFile(docx_path) as zf:
            for name in ['word/styles.xml', 'word/header1.xml', 'word/header2.xml', 
                         'word/header3.xml', 'word/footer1.xml', 'word/footer2.xml',
                         'word/footer3.xml', 'word/footnotes.xml', 'word/endnotes.xml',
                         'word/settings.xml', 'word/numbering.xml', 'word/fontTable.xml',
                         '[Content_Types].xml', 'word/_rels/document.xml.rels']:
                if name in zf.namelist():
                    parts[name] = zf.read(name).decode('utf-8', errors='replace')
    except Exception as e:
        parts['ERROR'] = str(e)
    return parts

def parse_styles(xml_content):
    """Parse styles from styles.xml, return list of (name, basedOn, type)."""
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    try:
        root = ET.fromstring(xml_content)
        styles = []
        for style_elem in root.findall('.//w:style', ns):
            style_type = style_elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}type', 'unknown')
            style_id = style_elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}styleId', '')
            name_elem = style_elem.find('.//w:name', ns)
            name = name_elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '') if name_elem is not None else ''
            based_on = ''
            based_elem = style_elem.find('.//w:basedOn', ns)
            if based_elem is not None:
                based_on = based_elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
            styles.append((style_id, name, style_type, based_on))
        return styles
    except ET.ParseError:
        return []

def parse_header_footer(xml_content):
    """Extract text content from header/footer XML."""
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    try:
        root = ET.fromstring(xml_content)
        texts = []
        for t in root.findall('.//w:t', ns):
            if t.text:
                texts.append(t.text)
        return ' | '.join(texts)
    except ET.ParseError:
        return ''

def analyze_sectpr(xml_content):
    """Extract section properties (margins, paper size)."""
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    try:
        root = ET.fromstring(xml_content)
        sectpr = root.find('.//w:sectPr', ns)
        if sectpr is None:
            return {}
        result = {}
        pg = sectpr.find('.//w:pgSz', ns)
        if pg is not None:
            result['page_w'] = pg.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}w', 'N/A')
            result['page_h'] = pg.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}h', 'N/A')
        margin = sectpr.find('.//w:pgMar', ns)
        if margin is not None:
            for attr in ['top', 'bottom', 'left', 'right', 'header', 'footer', 'gutter']:
                result[f'margin_{attr}'] = margin.get(
                    '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}' + attr, 'N/A')
        cols = sectpr.find('.//w:cols', ns)
        if cols is not None:
            result['cols_num'] = cols.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num', 'N/A')
        return result
    except ET.ParseError:
        return {}

def extract_journal_name_from_header(header_xml):
    """Extract journal name from header content."""
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    try:
        root = ET.fromstring(header_xml)
        texts = []
        for t in root.iter():
            tag = t.tag.split('}')[-1] if '}' in t.tag else t.tag
            if tag == 't' and t.text:
                texts.append(t.text)
        return ' '.join(texts).strip()
    except:
        return ''

def analyze_template(dot_path):
    """Full analysis of a single .dot template."""
    result = {
        'path': dot_path.name,
        'size_bytes': os.path.getsize(dot_path),
    }
    
    # Images
    images = extract_image_hashes(dot_path)
    result['images'] = images
    
    # XML parts
    parts = extract_xml_parts(dot_path)
    
    # Styles
    if 'word/styles.xml' in parts:
        styles = parse_styles(parts['word/styles.xml'])
        result['style_count'] = len(styles)
        result['style_ids'] = [s[0] for s in styles]
        result['style_names'] = [s[1] for s in styles]
    
    # Section props (from styles.xml which has sectPr for defaults)
    if 'word/styles.xml' in parts:
        result['sectpr'] = analyze_sectpr(parts['word/styles.xml'])
    
    # Headers
    for hdr_key in ['word/header1.xml', 'word/header2.xml', 'word/header3.xml']:
        if hdr_key in parts:
            result[hdr_key.replace('/', '_').replace('.xml', '')] = extract_journal_name_from_header(parts[hdr_key])
            # Also hash the full header content for comparison
            result[f'{hdr_key.replace("/", "_").replace(".xml", "")}_hash'] = hashlib.md5(parts[hdr_key].encode()).hexdigest()
    
    # Footers
    for ftr_key in ['word/footer1.xml', 'word/footer2.xml', 'word/footer3.xml']:
        if ftr_key in parts:
            result[ftr_key.replace('/', '_').replace('.xml', '')] = extract_journal_name_from_header(parts[ftr_key])
            result[f'{ftr_key.replace("/", "_").replace(".xml", "")}_hash'] = hashlib.md5(parts[ftr_key].encode()).hexdigest()
    
    # Settings
    if 'word/settings.xml' in parts:
        result['settings_hash'] = hashlib.md5(parts['word/settings.xml'].encode()).hexdigest()
    
    # Numbering
    if 'word/numbering.xml' in parts:
        result['numbering_hash'] = hashlib.md5(parts['word/numbering.xml'].encode()).hexdigest()
    
    # Font table
    if 'word/fontTable.xml' in parts:
        result['font_table_hash'] = hashlib.md5(parts['word/fontTable.xml'].encode()).hexdigest()
    
    # Content types
    if '[Content_Types].xml' in parts:
        result['content_types_hash'] = hashlib.md5(parts['[Content_Types].xml'].encode()).hexdigest()
    
    return result

def compare_all_templates():
    """Compare all 148 templates."""
    dot_files = sorted(TEMPLATES_DIR.glob('*.dot'))
    print(f"Total .dot files: {len(dot_files)}")
    print()
    
    results = {}
    for dot in dot_files:
        results[dot.name] = analyze_template(dot)
    
    # === 1. IMAGE COMPARISON ===
    print("=" * 80)
    print("1. IMAGE / LOGO ANALYSIS")
    print("=" * 80)
    
    image_groups = defaultdict(list)
    all_image_names = set()
    for fname, data in results.items():
        for img_path, img_hash in data.get('images', {}).items():
            all_image_names.add(img_path)
            image_groups[(img_path, img_hash)].append(fname)
    
    if image_groups:
        print(f"\nUnique images found: {len(image_groups)}")
        for (img_path, img_hash), files in sorted(image_groups.items()):
            shared = "UNIQUE (only in: " if len(files) == 1 else "SHARED ("
            shared += ", ".join(sorted(files)[:5])
            if len(files) > 5:
                shared += f" ... +{len(files)-5} more"
            shared += ")"
            print(f"  {img_path} (hash: {img_hash[:8]}) → {shared}")
    else:
        print("  No images embedded in any template")
    
    # === 2. HEADER COMPARISON ===
    print("\n" + "=" * 80)
    print("2. HEADER CONTENT COMPARISON")
    print("=" * 80)
    
    header_groups = defaultdict(list)
    for fname, data in results.items():
        for key in data:
            if key.endswith('_word_header1') or key.endswith('_word_header2') or key.endswith('_word_header3'):
                header_content = data.get(key, '')
                header_groups[(key, header_content)].append(fname)
    
    for (key, content), files in sorted(header_groups.items()):
        print(f"\n  {key}:")
        preview = content[:120] if content else "(empty)"
        print(f"    Content: {preview}")
        print(f"    Shared by {len(files)} templates")
        if len(files) <= 10:
            print(f"    Files: {', '.join(sorted(files))}")
        else:
            print(f"    Files: {', '.join(sorted(files)[:5])} ... +{len(files)-5} more")
    
    # === 3. FOOTER COMPARISON ===
    print("\n" + "=" * 80)
    print("3. FOOTER CONTENT COMPARISON")
    print("=" * 80)
    
    footer_groups = defaultdict(list)
    for fname, data in results.items():
        for key in data:
            if key.endswith('_word_footer1') or key.endswith('_word_footer2') or key.endswith('_word_footer3'):
                footer_content = data.get(key, '')
                footer_groups[(key, footer_content)].append(fname)
    
    for (key, content), files in sorted(footer_groups.items()):
        print(f"\n  {key}:")
        preview = content[:120] if content else "(empty)"
        print(f"    Content: {preview}")
        print(f"    Shared by {len(files)} templates")
    
    # === 4. STYLE COMPARISON ===
    print("\n" + "=" * 80)
    print("4. STYLE COUNT & COMPOSITION")
    print("=" * 80)
    
    style_counts = Counter()
    for fname, data in results.items():
        style_counts[data.get('style_count', 0)] += 1
    
    print(f"\nStyle count distribution:")
    for count, freq in sorted(style_counts.items()):
        print(f"  {count} styles → {freq} templates")
    
    # Check if all have same style IDs
    all_style_sets = {}
    for fname, data in results.items():
        all_style_sets[fname] = set(data.get('style_ids', []))
    
    if all_style_sets:
        first = list(all_style_sets.values())[0]
        same_styles = all(s == first for s in all_style_sets.values())
        print(f"\nAll templates have identical style IDs: {'✅ YES' if same_styles else '❌ NO'}")
        if not same_styles:
            # Find differences
            for fname, s_set in all_style_sets.items():
                if s_set != first:
                    print(f"  {fname}: diff = {s_set.symmetric_difference(first)}")
    
    # === 5. SECTION PROPERTIES (margins, page size) ===
    print("\n" + "=" * 80)
    print("5. SECTION PROPERTIES (margins, page size, columns)")
    print("=" * 80)
    
    sectpr_groups = defaultdict(list)
    for fname, data in results.items():
        sectpr = data.get('sectpr', {})
        key = json.dumps(sectpr, sort_keys=True)
        sectpr_groups[key].append(fname)
    
    for key, files in sectpr_groups.items():
        sectpr = json.loads(key)
        print(f"\n  Shared by {len(files)} templates:")
        for k, v in sectpr.items():
            print(f"    {k}: {v}")
        if len(files) > 146:
            print("    → ALL templates share these settings")
        elif len(files) <= 5:
            print(f"    Files: {', '.join(sorted(files))}")
    
    # === 6. SETTINGS, NUMBERING, FONT TABLE HASHES ===
    print("\n" + "=" * 80)
    print("6. SETTINGS / NUMBERING / FONT TABLE HASH COMPARISON")
    print("=" * 80)
    
    for xml_key in ['settings_hash', 'numbering_hash', 'font_table_hash', 'content_types_hash']:
        hash_groups = defaultdict(list)
        for fname, data in results.items():
            h = data.get(xml_key, 'MISSING')
            hash_groups[h].append(fname)
        
        unique_count = len(hash_groups)
        print(f"\n{xml_key}:")
        if unique_count == 1:
            print(f"  ✅ ALL {len(dot_files)} templates identical (hash: {list(hash_groups.keys())[0][:16]}...)")
        else:
            print(f"  ❌ {unique_count} unique hashes found:")
            for h, files in sorted(hash_groups.items(), key=lambda x: -len(x[1])):
                print(f"    {h[:12]}... → {len(files)} templates")
                if len(files) <= 5:
                    print(f"      Files: {', '.join(sorted(files))}")
    
    # === 7. HEADER/FULL HASH COMPARISON ===
    print("\n" + "=" * 80)
    print("7. FULL FILE SIZE & STRUCTURE")
    print("=" * 80)
    
    sizes = Counter()
    for fname, data in results.items():
        sizes[data['size_bytes']] += 1
    
    print(f"\nFile size distribution:")
    for size, freq in sorted(sizes.items()):
        print(f"  {size:,} bytes → {freq} templates")
    
    # === 8. IMAGE DETAIL - Extract actual image info ===
    print("\n" + "=" * 80)
    print("8. DETAILED IMAGE ANALYSIS (dimensions, format)")
    print("=" * 80)
    
    # Analyze a few sample templates for image details
    samples = list(dot_files)[:5]
    for dot_path in samples:
        print(f"\n  {dot_path.name}:")
        try:
            with zipfile.ZipFile(dot_path) as zf:
                for name in zf.namelist():
                    if name.startswith('word/media/'):
                        img_data = zf.read(name)
                        img = Image.open(io.BytesIO(img_data))
                        print(f"    {name}: {img.format}, {img.size[0]}x{img.size[1]}, {len(img_data):,} bytes")
        except Exception as e:
            print(f"    Error: {e}")
    
    return results

if __name__ == '__main__':
    results = compare_all_templates()
    
    # Save raw analysis for further inspection
    output = {}
    for fname, data in results.items():
        # Convert non-serializable
        clean = {}
        for k, v in data.items():
            if isinstance(v, set):
                clean[k] = sorted(v)
            else:
                clean[k] = v
        output[fname] = clean
    
    output_path = TEMPLATES_DIR.parent / 'autodocx_analysis.json'
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"\n\n📊 Full analysis saved to: {output_path}")
