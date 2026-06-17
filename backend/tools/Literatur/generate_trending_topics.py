"""
Generate 1,000 trending topics across 25 bidang for massive paper fetch.
Target: 1,000,000 papers (1,000 per topic × 1,000 topics)
Year range: 2015-2026
"""
import sys
import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "dbname": "paper_database",
    "user": "sirobo",
    "password": "paper2026",
}

# 25 bidang dengan trending topics per bidang
FIELDS = {
    "Akuntansi": [
        "financial accounting", "managerial accounting", "auditing", "tax accounting",
        "forensic accounting", "earnings management", "fair value accounting", "revenue recognition",
        "accounting ethics", "IFRS accounting", "sustainability accounting", "integrated reporting",
        "management control systems", "activity based costing", "corporate governance accounting",
        "public sector accounting", "Islamic accounting", "accounting information systems",
        "blockchain accounting", "ESG reporting", "carbon accounting", "environmental accounting",
        "audit quality", "internal audit", "audit committee", "accounting standards",
        "financial reporting", "cost accounting", "budgeting", "performance measurement",
        "accounting education", "accounting fraud", "whistleblowing accounting", "tax compliance",
        "tax avoidance", "transfer pricing accounting", "accounting digitalization", "fintech accounting",
        "crypto accounting", "accounting research",
    ],
    "Pajak": [
        "tax compliance", "tax avoidance", "tax evasion", "tax planning", "tax reform",
        "digital taxation", "carbon tax", "property tax", "VAT taxation", "international taxation",
        "tax incentives", "tax administration", "e-tax", "tax morale", "tax equity",
        "cryptocurrency taxation", "digital services tax", "BEPS OECD", "global minimum tax",
        "tax treaty", "transfer pricing", "tax audit", "tax dispute", "fiscal federalism",
        "SME taxation", "shadow economy taxation", "environmental tax", "sin tax", "wealth tax",
        "tax policy", "tax fairness", "tax collection efficiency", "tax revenue",
        "corporate taxation", "personal income tax", "tax incentives investment", "tax havens",
        "tax treaty shopping", "tax transparency", "tax automation", "tax digitalization",
    ],
    "Informasi dan Humas": [
        "public relations", "corporate communication", "crisis communication", "media relations",
        "social media communication", "digital public relations", "strategic communication",
        "organizational communication", "reputation management", "brand communication",
        "government communication", "political communication", "health communication",
        "environmental communication", "risk communication", "science communication",
        "journalism", "investigative journalism", "data journalism", "citizen journalism",
        "fake news", "misinformation", "disinformation", "fact checking",
        "media literacy", "information literacy", "digital literacy",
        "content marketing", "influencer marketing", "viral communication",
        "intercultural communication", "diplomacy communication",
        "information systems", "knowledge management", "data privacy communication",
        "AI communication", "chatbot communication", "automation communication",
        "virtual communication", "remote communication",
    ],
    "Manajemen Logistik": [
        "supply chain management", "logistics optimization", "warehouse management", "inventory control",
        "transportation logistics", "last mile delivery", "cold chain logistics", "reverse logistics",
        "green logistics", "sustainable supply chain", "circular supply chain",
        "supply chain resilience", "supply chain risk management", "supply chain disruption",
        "procurement strategy", "supplier selection", "demand forecasting", "demand planning",
        "lean logistics", "agile supply chain", "just in time logistics",
        "blockchain supply chain", "IoT supply chain", "AI supply chain",
        "digital twin logistics", "autonomous vehicles logistics", "drone delivery",
        "vehicle routing problem", "fleet management", "route optimization",
        "port logistics", "maritime logistics", "intermodal transportation",
        "e-commerce logistics", "omnichannel logistics", "fulfillment center",
        "humanitarian logistics", "disaster relief logistics", "military logistics",
        "food supply chain", "pharmaceutical logistics",
    ],
    "Ekonomi": [
        "economic growth", "inflation", "unemployment", "monetary policy", "fiscal policy",
        "international trade", "exchange rate", "foreign direct investment", "economic development",
        "poverty", "inequality", "labor economics", "human capital", "education economics",
        "health economics", "environmental economics", "natural resource economics",
        "industrial organization", "market competition", "antitrust policy",
        "behavioral economics", "experimental economics", "game theory economics",
        "financial economics", "banking", "capital markets", "investment",
        "macroeconomics", "microeconomics", "econometrics",
        "development economics", "institutional economics", "political economy",
        "digital economy", "platform economy", "gig economy", "creative economy",
        "Islamic economics", "sustainable economics", "circular economy",
    ],
    "Teknik Mesin": [
        "mechanical design", "thermodynamics", "fluid mechanics", "heat transfer",
        "materials science", "composite materials", "manufacturing processes", "CNC machining",
        "3D printing additive manufacturing", "welding technology", "casting", "forging",
        "tribology friction wear", "lubrication", "bearing design",
        "vibration analysis", "noise control", "structural dynamics",
        "robotics", "mechatronics", "automation", "control systems",
        "internal combustion engine", "gas turbine", "steam turbine",
        "renewable energy systems", "solar thermal", "wind turbine", "geothermal",
        "HVAC systems", "refrigeration", "air conditioning",
        "automotive engineering", "aerospace engineering", "marine engineering",
        "finite element analysis", "computational fluid dynamics", "simulation",
        "quality control", "reliability engineering", "maintenance",
    ],
    "Teknik Listrik": [
        "power systems", "power electronics", "electric machines", "motor control",
        "renewable energy integration", "smart grid", "microgrid", "energy storage",
        "battery technology", "lithium ion battery", "supercapacitor",
        "high voltage engineering", "insulation", "power quality",
        "power transmission", "power distribution", "substation",
        "protection systems", "relay protection", "fault analysis",
        "control systems", "PLC programming", "SCADA", "industrial automation",
        "embedded systems", "microcontroller", "FPGA", "VHDL",
        "signal processing", "digital signal processing", "image processing",
        "telecommunications", "wireless communication", "5G technology", "antenna",
        "IoT systems", "sensor networks", "wireless sensor network",
        "electric vehicles", "charging infrastructure", "vehicle to grid",
        "solar PV systems", "wind energy conversion",
    ],
    "Teknik Sipil": [
        "structural engineering", "concrete technology", "reinforced concrete", "prestressed concrete",
        "steel structures", "composite structures", "timber structures",
        "geotechnical engineering", "soil mechanics", "foundation engineering", "slope stability",
        "transportation engineering", "pavement design", "traffic engineering", "highway engineering",
        "hydraulic engineering", "hydrology", "water resources", "flood management",
        "construction management", "project management", "cost estimation",
        "building materials", "sustainable construction", "green building",
        "earthquake engineering", "seismic design", "structural dynamics",
        "bridge engineering", "tunnel engineering", "underground construction",
        "urban planning", "smart cities", "infrastructure planning",
        "BIM building information modeling", "construction technology", "3D printing construction",
        "construction safety", "quality control construction", "building codes",
    ],
    "Arsitektur": [
        "architectural design", "building design", "space planning", "form and space",
        "sustainable architecture", "green architecture", "passive design", "bioclimatic design",
        "tropical architecture", "vernacular architecture", "traditional architecture",
        "modern architecture", "contemporary architecture", "postmodern architecture",
        "urban design", "urban planning", "public space design", "landscape architecture",
        "interior design", "interior architecture", "furniture design",
        "building technology", "construction materials", "building envelope",
        "thermal comfort", "natural ventilation", "daylighting", "acoustic design",
        "housing design", "residential architecture", "social housing",
        "commercial architecture", "office design", "retail design",
        "heritage conservation", "adaptive reuse", "restoration architecture",
        "parametric design", "digital architecture", "computational design",
        "BIM architecture", "building performance simulation",
    ],
    "Perkapalan": [
        "ship design", "naval architecture", "hydrodynamics", "ship resistance",
        "ship propulsion", "marine engineering", "marine machinery", "ship systems",
        "ship construction", "shipbuilding", "ship repair", "ship maintenance",
        "ship stability", "ship safety", "ship operations", "port operations",
        "marine transportation", "shipping logistics", "maritime transport",
        "offshore engineering", "oil platform", "floating production", "subsea systems",
        "ship automation", "unmanned vessels", "autonomous ships",
        "green shipping", "emission control", "ballast water treatment",
        "ship financing", "maritime law", "maritime insurance",
        "container shipping", "bulk shipping", "tanker operations",
        "ship recycling", "ship breaking", "end of life ships",
        "marine renewable energy", "ocean thermal energy", "wave energy",
    ],
    "Perencanaan Wilayah dan Kota": [
        "urban planning", "regional planning", "spatial planning", "land use planning",
        "urban design", "public space", "placemaking", "urban regeneration",
        "smart cities", "sustainable cities", "green cities", "resilient cities",
        "urban transportation", "transit oriented development", "walkability", "bikeability",
        "urban housing", "affordable housing", "social housing", "housing policy",
        "urban infrastructure", "urban utilities", "urban services",
        "urban environment", "urban green space", "urban heat island",
        "urban economics", "urban development", "urban growth", "urban sprawl",
        "urban governance", "participatory planning", "community planning",
        "disaster planning", "climate adaptation", "urban resilience",
        "heritage conservation urban", "urban tourism", "urban culture",
        "urban informatics", "GIS urban planning", "spatial analysis",
    ],
    "Lingkungan": [
        "environmental science", "environmental engineering", "environmental management",
        "pollution control", "air pollution", "water pollution", "soil pollution", "noise pollution",
        "waste management", "solid waste", "hazardous waste", "waste to energy", "recycling",
        "water treatment", "wastewater treatment", "water quality", "water resources",
        "air quality", "emission control", "carbon capture", "carbon sequestration",
        "climate change", "global warming", "greenhouse gas", "carbon footprint",
        "environmental impact assessment", "environmental monitoring", "environmental auditing",
        "biodiversity", "conservation", "ecosystem services", "restoration ecology",
        "sustainable development", "sustainability", "circular economy", "green economy",
        "environmental policy", "environmental law", "environmental governance",
        "renewable energy", "clean energy", "energy efficiency",
        "environmental education", "environmental awareness", "environmental behavior",
    ],
    "Kelautan": [
        "oceanography", "physical oceanography", "chemical oceanography", "biological oceanography",
        "marine biology", "marine ecology", "marine biodiversity", "coral reef",
        "fisheries", "fisheries management", "aquaculture", "mariculture",
        "marine conservation", "marine protected area", "marine spatial planning",
        "coastal management", "coastal erosion", "coastal protection", "coastal zone",
        "marine pollution", "marine debris", "plastic pollution ocean", "oil spill",
        "marine resources", "mineral resources ocean", "deep sea mining",
        "ocean energy", "wave energy", "tidal energy", "ocean thermal energy",
        "marine technology", "underwater technology", "subsea engineering",
        "marine transportation", "shipping", "port management",
        "marine law", "UNCLOS", "maritime boundaries",
        "climate change ocean", "ocean acidification", "sea level rise",
    ],
    "Perikanan": [
        "fisheries management", "aquaculture", "mariculture", "fish farming",
        "fish nutrition", "fish health", "fish disease", "fish immunology",
        "fish genetics", "fish breeding", "fish reproduction",
        "fisheries biology", "fish population dynamics", "stock assessment",
        "fisheries economics", "fisheries policy", "fisheries governance",
        "fisheries technology", "fishing gear", "fishing vessel",
        "post harvest fisheries", "fish processing", "fish preservation",
        "seafood safety", "seafood quality", "seafood traceability",
        "sustainable fisheries", "responsible fisheries", "ecosystem approach fisheries",
        "small scale fisheries", "artisanal fisheries", "industrial fisheries",
        "inland fisheries", "freshwater fisheries", "capture fisheries",
        "fisheries co management", "community based fisheries", "fisheries certification",
        "fisheries data", "fisheries statistics", "fisheries monitoring",
    ],
    "Psikologi": [
        "clinical psychology", "counseling psychology", "educational psychology", "social psychology",
        "developmental psychology", "cognitive psychology", "behavioral psychology", "neuropsychology",
        "industrial organizational psychology", "workplace psychology", "occupational health",
        "health psychology", "stress management", "mental health", "wellbeing",
        "positive psychology", "happiness", "life satisfaction", "resilience",
        "psychological assessment", "psychological testing", "psychometrics",
        "psychotherapy", "cognitive behavioral therapy", "mindfulness",
        "child psychology", "adolescent psychology", "adult development", "aging",
        "forensic psychology", "criminal psychology", "legal psychology",
        "sport psychology", "exercise psychology", "performance psychology",
        "consumer psychology", "marketing psychology", "decision making",
        "group dynamics", "leadership psychology", "motivation",
        "cultural psychology", "cross cultural psychology", "indigenous psychology",
        "cyberpsychology", "digital psychology", "social media psychology",
    ],
    "Kimia": [
        "organic chemistry", "inorganic chemistry", "physical chemistry", "analytical chemistry",
        "biochemistry", "medicinal chemistry", "pharmaceutical chemistry",
        "polymer chemistry", "materials chemistry", "nanomaterials",
        "catalysis", "heterogeneous catalysis", "homogeneous catalysis", "biocatalysis",
        "green chemistry", "sustainable chemistry", "environmental chemistry",
        "electrochemistry", "photochemistry", "spectroscopy",
        "chemical engineering", "reaction engineering", "process engineering",
        "separation technology", "membrane technology", "distillation",
        "food chemistry", "natural products", "essential oils", "phytochemistry",
        "industrial chemistry", "petrochemicals", "fine chemicals",
        "computational chemistry", "molecular modeling", "quantum chemistry",
        "supramolecular chemistry", "coordination chemistry", "organometallic chemistry",
        "surface chemistry", "colloid chemistry", "interface chemistry",
    ],
    "Teknik Industri": [
        "industrial engineering", "operations research", "optimization", "simulation",
        "production planning", "production control", "scheduling", "inventory management",
        "quality management", "quality control", "Six Sigma", "lean manufacturing",
        "supply chain management", "logistics", "procurement",
        "ergonomics", "human factors", "workplace design", "occupational safety",
        "industrial automation", "robotics", "mechatronics", "Industry 4.0",
        "manufacturing systems", "production systems", "flexible manufacturing",
        "facility layout", "plant design", "material handling",
        "project management", "risk management", "decision analysis",
        "engineering economics", "cost analysis", "investment analysis",
        "sustainable manufacturing", "green manufacturing", "circular economy manufacturing",
        "digital manufacturing", "smart manufacturing", "additive manufacturing",
        "maintenance management", "reliability engineering", "total productive maintenance",
    ],
    "Otomasi": [
        "industrial automation", "PLC programming", "SCADA", "DCS distributed control",
        "process control", "PID control", "advanced process control", "model predictive control",
        "robotics", "industrial robot", "collaborative robot", "robot programming",
        "machine vision", "computer vision", "image processing", "pattern recognition",
        "artificial intelligence", "machine learning", "deep learning", "neural network",
        "IoT industrial", "Industrial Internet of Things", "sensor network",
        "cyber physical systems", "digital twin", "smart factory",
        "automation systems", "control systems", "mechatronics",
        "electric drives", "motor control", "servo systems", "stepper motor",
        "hydraulic systems", "pneumatic systems", "actuator",
        "HMI human machine interface", "operator interface", "visualization",
        "embedded systems", "microcontroller", "real time systems",
        "autonomous systems", "unmanned systems", "drone automation",
    ],
    "Otomotif": [
        "automotive engineering", "vehicle design", "vehicle dynamics", "vehicle safety",
        "internal combustion engine", "diesel engine", "gasoline engine", "engine performance",
        "engine emission", "emission control", "catalytic converter", "exhaust gas",
        "alternative fuels", "biofuel", "hydrogen fuel cell", "electric vehicle",
        "hybrid vehicle", "plug in hybrid", "battery electric vehicle",
        "vehicle transmission", "gearbox", "clutch", "differential",
        "vehicle suspension", "steering system", "brake system",
        "automotive electronics", "ECU engine control", "vehicle sensor",
        "autonomous vehicle", "self driving car", "ADAS advanced driver assistance",
        "vehicle aerodynamics", "vehicle crashworthiness", "vehicle NVH",
        "automotive manufacturing", "automotive materials", "lightweight vehicle",
        "vehicle maintenance", "automotive diagnostics", "OBD on board diagnostic",
        "connected vehicle", "vehicle to vehicle", "vehicle to infrastructure",
    ],
    "Bahasa Asing": [
        "English language teaching", "second language acquisition", "foreign language learning",
        "language pedagogy", "language curriculum", "language assessment", "language testing",
        "TESOL", "TEFL", "applied linguistics", "sociolinguistics", "psycholinguistics",
        "discourse analysis", "pragmatics", "semantics", "syntax", "morphology",
        "translation studies", "interpretation", "translation technology",
        "language technology", "natural language processing", "machine translation",
        "corpus linguistics", "computational linguistics", "language resources",
        "English for specific purposes", "English for academic purposes", "English for business",
        "language policy", "language planning", "language education policy",
        "multilingualism", "bilingualism", "code switching", "translanguaging",
        "intercultural communication", "cross cultural communication", "language and culture",
        "language teacher education", "teacher professional development", "reflective teaching",
        "computer assisted language learning", "mobile language learning", "online language learning",
        "language learner autonomy", "language learning strategies", "learner motivation",
    ],
    "Teknologi Pangan": [
        "food science", "food technology", "food engineering", "food processing",
        "food safety", "food quality", "food microbiology", "food preservation",
        "food chemistry", "food analysis", "food composition", "food nutrition",
        "functional food", "nutraceuticals", "bioactive compounds", "food fortification",
        "food packaging", "active packaging", "intelligent packaging", "biodegradable packaging",
        "food biotechnology", "fermentation", "enzyme technology", "probiotics",
        "food rheology", "food texture", "food sensory", "food flavor",
        "food waste", "food loss", "food waste valorization", "food byproduct",
        "traditional food", "ethnic food", "local food", "indigenous food",
        "food innovation", "new product development", "food formulation",
        "food regulation", "food labeling", "food standards",
        "sustainable food systems", "food security", "food sovereignty",
    ],
    "Farmasi": [
        "pharmaceutical science", "pharmaceutics", "pharmacology", "pharmacokinetics",
        "drug discovery", "drug design", "medicinal chemistry", "pharmaceutical chemistry",
        "pharmaceutical technology", "drug delivery", "nanomedicine", "targeted drug delivery",
        "pharmaceutical analysis", "quality control pharmaceutical", "pharmaceutical validation",
        "pharmaceutical manufacturing", "GMP good manufacturing practice", "pharmaceutical regulation",
        "pharmacognosy", "herbal medicine", "traditional medicine", "phytotherapy",
        "clinical pharmacy", "pharmacovigilance", "drug safety", "adverse drug reaction",
        "pharmaceutical microbiology", "sterile products", "biopharmaceuticals",
        "pharmaceutical biotechnology", "biologics", "vaccine development", "gene therapy",
        "pharmaceutical economics", "pharmacoeconomics", "health technology assessment",
        "pharmaceutical marketing", "pharmaceutical supply chain", "drug distribution",
        "pharmaceutical education", "pharmacy practice", "community pharmacy",
    ],
    "Kesehatan": [
        "public health", "epidemiology", "biostatistics", "health promotion", "health education",
        "health policy", "health systems", "health management", "health economics",
        "clinical medicine", "internal medicine", "surgery", "pediatrics", "obstetrics gynecology",
        "nursing", "nursing care", "nursing education", "nursing practice",
        "nutrition", "dietetics", "clinical nutrition", "community nutrition",
        "mental health", "psychiatry", "psychology health",
        "reproductive health", "maternal health", "child health", "adolescent health",
        "infectious diseases", "communicable diseases", "non communicable diseases",
        "environmental health", "occupational health", "workplace health",
        "health informatics", "digital health", "telemedicine", "e health",
        "global health", "international health", "tropical medicine",
        "health quality", "patient safety", "healthcare quality",
    ],
    "Biologi": [
        "molecular biology", "cell biology", "genetics", "genomics", "proteomics",
        "microbiology", "bacteriology", "virology", "mycology", "parasitology",
        "ecology", "population ecology", "community ecology", "ecosystem ecology",
        "evolutionary biology", "phylogenetics", "systematics", "taxonomy",
        "biotechnology", "genetic engineering", "CRISPR", "gene editing",
        "plant biology", "botany", "plant physiology", "plant breeding",
        "animal biology", "zoology", "entomology", "ornithology",
        "marine biology", "aquatic biology", "fisheries biology",
        "immunology", "immunotherapy", "vaccine",
        "developmental biology", "stem cells", "regenerative biology",
        "conservation biology", "biodiversity", "wildlife biology",
        "bioinformatics", "computational biology", "systems biology",
        "synthetic biology", "industrial biology", "bioprocess",
    ],
    "Fisika": [
        "classical mechanics", "quantum mechanics", "statistical mechanics", "thermodynamics",
        "electromagnetism", "optics", "photonics", "laser",
        "condensed matter physics", "solid state physics", "materials physics",
        "nuclear physics", "particle physics", "high energy physics",
        "astrophysics", "cosmology", "astronomy", "space physics",
        "atomic physics", "molecular physics", "chemical physics",
        "plasma physics", "fusion energy", "plasma technology",
        "acoustics", "ultrasound", "sonic",
        "fluid dynamics", "aerodynamics", "hydrodynamics",
        "biophysics", "medical physics", "radiation physics",
        "geophysics", "seismology", "atmospheric physics",
        "nanotechnology", "nanoscience", "nanomaterials physics",
        "computational physics", "numerical methods", "simulation physics",
        "renewable energy physics", "solar energy", "wind energy physics",
    ],
}

def main():
    conn = psycopg2.connect(
        host=DB_CONFIG["host"],
        dbname=DB_CONFIG["dbname"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )
    cur = conn.cursor()
    
    # Count existing topics
    cur.execute("SELECT count(*) FROM mega_fetch_progress WHERE status='pending'")
    existing = cur.fetchone()[0]
    
    if existing > 0:
        print(f"⚠️  Ada {existing} topik pending. Reset atau skip? (reset/skip)", file=sys.stderr)
        # Auto reset for this run
        print("Auto-resetting pending topics...", file=sys.stderr)
        cur.execute("DELETE FROM mega_fetch_progress WHERE status='pending'")
        conn.commit()
    
    # Generate topics: 25 bidang × 40 topics = 1,000 topics
    # Target: 1,000 papers per topic = 1,000,000 total
    TARGET_PER_TOPIC = 1000
    
    inserted = 0
    for field, topics in FIELDS.items():
        for topic in topics:
            # Compose field_name with field prefix
            field_name = f"!{field[:50]}"
            
            # Insert into mega_fetch_progress
            cur.execute("""
                INSERT INTO mega_fetch_progress (field_name, topic, target_count, status)
                VALUES (%s, %s, %s, 'pending')
                ON CONFLICT (field_name, topic) DO UPDATE SET
                    target_count = EXCLUDED.target_count,
                    status = 'pending',
                    updated_at = NOW()
            """, (field_name, topic, TARGET_PER_TOPIC))
            inserted += 1
    
    conn.commit()
    
    # Summary
    cur.execute("SELECT status, count(*), sum(target_count) FROM mega_fetch_progress WHERE status='pending' GROUP BY status")
    row = cur.fetchone()
    print(f"\n✅ Inserted {inserted} trending topics")
    print(f"   Target: {row[2]:,} papers ({row[1]} topics × {TARGET_PER_TOPIC:,} papers)")
    print(f"   Year range: 2015-2026")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
