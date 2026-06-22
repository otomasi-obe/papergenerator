#!/usr/bin/env python3
"""Autodocx Phase 2: Deep header/content analysis + outlier comparison."""

import json
import hashlib
import zipfile
import io
import re
from pathlib import Path
from collections import defaultdict
from xml.etree import ElementTree as ET

TEMPLATES_DIR = Path("/home/sirobo/papergenerator/backend/tools/Journal/mdpi_templates")

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
VML_NS = 'urn:schemas-microsoft-com:vml'

def get_xml_part(docx_path, part_name):
    try:
        with zipfile.ZipFile(docx_path) as zf:
            for name in zf.namelist():
                if name.endswith(part_name):
                    return zf.read(name).decode('utf-8', errors='replace')
    except:
        return None

def parse_all_texts(xml_content):
    """Extract all w:t text nodes with structure info."""
    ns = {'w': W_NS, 'r': R_NS, 'v': VML_NS}
    if not xml_content:
        return []
    try:
        root = ET.fromstring(xml_content)
        results = []
        for t in root.iter():
            tag = t.tag.split('}')[-1] if '}' in t.tag else t.tag
            if tag == 't' and t.text:
                results.append(t.text)
        return results
    except:
        return []

def parse_header_parts(docx_path):
    """Parse all header/footer XML parts with their relationship info."""
    # Get rels to find which header is default/even/first
    rels_xml = get_xml_part(docx_path, 'document.xml.rels')
    if not rels_xml:
        return {}
    
    # Parse relationships
    ns = {'rel': R_NS, 'ct': 'http://schemas.openxmlformats.org/package/2006/content-types'}
    try:
        root = ET.fromstring(rels_xml)
        header_map = {}  # rId -> type
        for rel in root.findall('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship'):
            rid = rel.get('Id', '')
            target = rel.get('Target', '')
            rtype = rel.get('Type', '')
            if 'header' in rtype.lower():
                header_map[target] = 'header'
            elif 'footer' in rtype.lower():
                header_map[target] = 'footer'
    except:
        pass

    # Parse [Content_Types].xml to find overrides
    ct_xml = get_xml_part(docx_path, '[Content_Types].xml')
    
    # Get all XML parts from the zip
    result = {'headers': {}, 'footers': {}, 'document_texts': []}
    try:
        with zipfile.ZipFile(docx_path) as zf:
            for name in zf.namelist():
                texts = []
                if name.startswith('word/') and name.endswith('.xml'):
                    content = zf.read(name).decode('utf-8', errors='replace')
                    texts = parse_all_texts(content)
                    
                    if 'header' in name:
                        key = name.replace('word/', '')
                        result['headers'][key] = {'texts': texts, 'all_text': ' '.join(texts)}
                    elif 'footer' in name:
                        key = name.replace('word/', '')
                        result['footers'][key] = {'texts': texts, 'all_text': ' '.join(texts)}
                    elif name == 'word/document.xml':
                        result['document_texts'] = texts
    except Exception as e:
        result['error'] = str(e)
    
    return result

def deep_compare_images(dot_path):
    """Extract image metadata: hash, dimensions, file size."""
    from PIL import Image
    images = []
    try:
        with zipfile.ZipFile(dot_path) as zf:
            for name in sorted(zf.namelist()):
                if name.startswith('word/media/'):
                    img_data = zf.read(name)
                    h = hashlib.md5(img_data).hexdigest()
                    img = Image.open(io.BytesIO(img_data))
                    images.append({
                        'path': name.replace('word/media/', ''),
                        'hash': h,
                        'format': img.format,
                        'width': img.size[0],
                        'height': img.size[1],
                        'size_bytes': len(img_data),
                    })
    except Exception as e:
        pass
    return images

def analyze_styles_detail(xml_content):
    """Parse styles with font and paragraph details."""
    ns = {'w': W_NS}
    if not xml_content:
        return []
    try:
        root = ET.fromstring(xml_content)
        styles = []
        for style_elem in root.findall('.//w:style', ns):
            style_id = style_elem.get(f'{{{W_NS}}}styleId', '')
            style_type = style_elem.get(f'{{{W_NS}}}type', '')
            name_elem = style_elem.find('.//w:name', ns)
            name = name_elem.get(f'{{{W_NS}}}val', '') if name_elem is not None else ''
            
            # Fonts
            rpr = style_elem.find('.//w:rPr', ns)
            fonts = {}
            if rpr is not None:
                rfonts = rpr.find('.//w:rFonts', ns)
                if rfonts is not None:
                    fonts['ascii'] = rfonts.get(f'{{{W_NS}}}ascii', '')
                    fonts['hAnsi'] = rfonts.get(f'{{{W_NS}}}hAnsi', '')
                    fonts['cs'] = rfonts.get(f'{{{W_NS}}}cs', '')
                sz = rpr.find('.//w:sz', ns)
                if sz is not None:
                    fonts['size'] = sz.get(f'{{{W_NS}}}val', '')
            
            styles.append({
                'id': style_id,
                'name': name,
                'type': style_type,
                'fonts': fonts,
            })
        return styles
    except:
        return []

# ===== MAIN ANALYSIS =====

dot_files = sorted(TEMPLATES_DIR.glob('*.dot'))
print(f"Phase 2: Deep analysis of {len(dot_files)} templates")
print()

# 1. Deep header/footer analysis
print("=" * 80)
print("1. HEADER / FOOTER TEXT CONTENT")
print("=" * 80)

# Analyze 5 samples + all outliers
samples = [
    'acoustics-template.dot',
    'admsci-template.dot', 
    'fossils-template.dot',
    'brainsci-template.dot',
    'galaxies-template.dot',
    'hardware-template.dot',
    'ijms-template.dot',
    'informatics-template.dot',
]

for dot_name in samples:
    dot_path = TEMPLATES_DIR / dot_name
    if not dot_path.exists():
        continue
    
    result = parse_header_parts(dot_path)
    print(f"\n{'─'*60}")
    print(f"📄 {dot_name}")
    
    # Headers
    print(f"  Headers:")
    for hdr_key, hdr_data in sorted(result.get('headers', {}).items()):
        text = hdr_data.get('all_text', '')
        preview = text[:200] if text else '(EMPTY)'
        print(f"    {hdr_key}: {preview}")
    
    # Footers
    print(f"  Footers:")
    for ftr_key, ftr_data in sorted(result.get('footers', {}).items()):
        text = ftr_data.get('all_text', '')
        preview = text[:200] if text else '(EMPTY)'
        print(f"    {ftr_key}: {preview}")
    
    # Document first texts
    doc_texts = result.get('document_texts', [])
    if doc_texts:
        first_texts = ' | '.join(doc_texts[:10])
        print(f"  Document first texts: {first_texts[:200]}")

# 2. Image comparison summary
print("\n" + "=" * 80)
print("2. IMAGE DIMENSION SUMMARY")
print("=" * 80)

# Group image3 by dimensions
img3_groups = defaultdict(list)
all_images = {}

for dot in dot_files:
    images = deep_compare_images(dot)
    for img in images:
        if img['path'] not in all_images:
            all_images[img['path']] = defaultdict(list)
        key = (img['width'], img['height'], img['size_bytes'])
        all_images[img['path']][key].append(dot.name)

for img_name in sorted(all_images.keys()):
    dimensions = all_images[img_name]
    print(f"\n  {img_name}:")
    for (w, h, sz), files in sorted(dimensions.items()):
        n = len(files)
        if n > 140:
            print(f"    {w}x{h}, {sz:,} bytes → ALL {n} templates (identical)")
        elif n > 10:
            print(f"    {w}x{h}, {sz:,} bytes → {n} templates")
        else:
            print(f"    {w}x{h}, {sz:,} bytes → {n} templates: {', '.join(sorted(files)[:5])}{'...' if len(files)>5 else ''}")

# 3. Compare two typical templates in full XML detail
print("\n" + "=" * 80)
print("3. FULL XML COMPARISON: acoustics vs admsci")
print("=" * 80)

def compare_xml_parts(path1, path2):
    """Compare all XML parts and show differences."""
    parts1 = {}
    parts2 = {}
    with zipfile.ZipFile(path1) as zf1, zipfile.ZipFile(path2) as zf2:
        for name in zf1.namelist():
            if name.endswith('.xml'):
                parts1[name] = zf1.read(name).decode('utf-8', errors='replace')
        for name in zf2.namelist():
            if name.endswith('.xml'):
                parts2[name] = zf2.read(name).decode('utf-8', errors='replace')
    
    all_parts = sorted(set(parts1.keys()) | set(parts2.keys()))
    for part in all_parts:
        in1 = part in parts1
        in2 = part in parts2
        if in1 and in2:
            same = parts1[part] == parts2[part]
            if not same:
                # Find first difference
                t1 = parts1[part]
                t2 = parts2[part]
                diff_pos = None
                for i in range(min(len(t1), len(t2))):
                    if t1[i] != t2[i]:
                        diff_pos = i
                        break
                ctx = 50
                if diff_pos:
                    pre = t1[max(0,diff_pos-ctx):diff_pos-1]
                    p1 = t1[diff_pos:diff_pos+ctx]
                    p2 = t2[diff_pos:diff_pos+ctx]
                    print(f"\n  ✗ {part} DIFFERS at offset {diff_pos}")
                    print(f"    Before: ...{pre[-60:]}...")
                    print(f"    A:      {p1[:80]}")
                    print(f"    B:      {p2[:80]}")
            else:
                pass  # identical
        elif in1 and not in2:
            print(f"\n  → {part}: ONLY in acoustics")

compare_xml_parts(TEMPLATES_DIR / 'acoustics-template.dot', TEMPLATES_DIR / 'admsci-template.dot')

# 4. fossils analysis
print("\n" + "=" * 80)
print("4. FOSSILS OUTLIER DEEP ANALYSIS")
print("=" * 80)

fossils_path = TEMPLATES_DIR / 'fossils-template.dot'
acoustics_path = TEMPLATES_DIR / 'acoustics-template.dot'

ff_styles = analyze_styles_detail(get_xml_part(fossils_path, 'styles.xml'))
ac_styles = analyze_styles_detail(get_xml_part(acoustics_path, 'styles.xml'))

ff_ids = {s['id'] for s in ff_styles}
ac_ids = {s['id'] for s in ac_styles}

print(f"\n  Fossils styles: {len(ff_styles)}, Acoustics styles: {len(ac_styles)}")
print(f"  Extra in fossils: {sorted(ff_ids - ac_ids)}")
print(f"  Missing from fossils: {sorted(ac_ids - ff_ids)}")

# Print fossils-unique styles
print(f"\n  Fossils-unique style details:")
for s in ff_styles:
    if s['id'] in (ff_ids - ac_ids):
        print(f"    {s['id']} ({s['type']}): name='{s['name']}', fonts={s['fonts']}")

# Check if fossils has document.xml or just template structure
fossils_doc = get_xml_part(fossils_path, 'document.xml')
if fossils_doc:
    texts = parse_all_texts(fossils_doc)
    print(f"\n  Document text content ({len(texts)} text nodes):")
    for t in texts[:30]:
        print(f"    '{t}'")
else:
    print(f"\n  No document.xml found")
    
# Check what's in fossils zip
print(f"\n  Fossils zip contents:")
with zipfile.ZipFile(fossils_path) as zf:
    for name in sorted(zf.namelist()):
        print(f"    {name} ({zf.getinfo(name).file_size:,} bytes)")

print("\n" + "=" * 80)
print("5. brainsci / galaxies / hardware OUTLIER CHECK")
print("=" * 80)

for dot_name in ['brainsci-template.dot', 'galaxies-template.dot', 'hardware-template.dot']:
    dot_path = TEMPLATES_DIR / dot_name
    if not dot_path.exists():
        continue
    styles_detail = analyze_styles_detail(get_xml_part(dot_path, 'styles.xml'))
    s_ids = {s['id'] for s in styles_detail}
    extra = s_ids - ac_ids
    missing = ac_ids - s_ids
    print(f"\n  {dot_name}:")
    print(f"    Styles: {len(styles_detail)}, Extra: {sorted(extra)}, Missing: {sorted(missing)}")

print("\n\n✅ Analysis complete.")