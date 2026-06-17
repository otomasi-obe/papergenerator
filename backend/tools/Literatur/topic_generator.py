"""
Mega Fetch — Topic Generator V3
25 bidang × 100 trending topics, curated per bidang.
"""
import requests
import time
import json
import sys
import os
import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "dbname": "paper_database",
    "user": "sirobo",
    "password": "paper2026",
}

# 25 bidang sesuai permintaan user
FIELDS_TOPICS = {
    "Akuntansi": {
        "concept_id": "C161191863",
        "seeds": [
            "financial accounting", "managerial accounting", "cost accounting", "tax accounting",
            "auditing", "forensic accounting", "financial reporting", "earnings management",
            "fair value accounting", "goodwill impairment", "revenue recognition", "lease accounting",
            "consolidation accounting", "intercompany transactions", "foreign currency translation",
            "hedging accounting", "pension accounting", "stock compensation accounting",
            "environmental accounting", "social accounting", "sustainability reporting",
            "integrated reporting", "management control systems", "balanced scorecard",
            "activity based costing", "target costing", "kaizen costing", "life cycle costing",
            "transfer pricing", "tax planning", "tax avoidance", "tax compliance",
            "audit quality", "audit fees", "internal audit", "audit committee",
            "corporate governance accounting", "board independence", "executive compensation",
            "accounting standards IFRS", "accounting convergence", "accounting ethics",
            "public sector accounting", "government accounting", "not for profit accounting",
            "Islamic accounting", "Shariah accounting", "zakat accounting",
            "accounting information systems", "ERP systems accounting", "blockchain accounting",
        ]
    },
    "Pajak": {
        "concept_id": "C161191863",
        "seeds": [
            "tax policy", "tax reform", "tax compliance", "tax avoidance",
            "tax evasion", "tax planning", "transfer pricing", "tax havens",
            "corporate taxation", "personal income tax", "value added tax", "goods services tax",
            "digital economy taxation", "BEPS base erosion", "OECD tax framework",
            "double taxation treaty", "tax treaty abuse", "treaty shopping",
            "carbon tax", "environmental tax", "sin tax", "luxury tax",
            "property tax", "land value tax", "wealth tax", "inheritance tax",
            "tax incentives", "tax holidays", "investment tax credit", "R&D tax credit",
            "tax administration", "e-tax", "digital tax filing", "tax collection efficiency",
            "tax morale", "tax fairness", "tax equity", "progressive taxation",
            "international taxation", "global minimum tax", "Pillar Two OECD",
            "cryptocurrency taxation", "digital services tax", "e-commerce taxation",
            "SME taxation", "informal sector taxation", "shadow economy taxation",
            "tax audit", "tax dispute resolution", "tax court",
            "fiscal federalism", "intergovernmental fiscal transfers",
        ]
    },
    "Informasi dan Humas": {
        "concept_id": "C41008148",
        "seeds": [
            "public relations", "corporate communication", "crisis communication", "media relations",
            "social media communication", "digital public relations", "strategic communication",
            "organizational communication", "internal communication", "stakeholder engagement",
            "reputation management", "brand communication", "corporate storytelling",
            "government communication", "political communication", "health communication",
            "environmental communication", "risk communication", "science communication",
            "media literacy", "information literacy", "digital literacy",
            "journalism", "investigative journalism", "data journalism", "citizen journalism",
            "fake news", "misinformation", "disinformation", "fact checking",
            "media effects", "agenda setting theory", "framing theory", "uses gratifications",
            "public opinion", "polling methodology", "survey research communication",
            "advertising communication", "marketing communication", "integrated marketing",
            "content marketing", "influencer marketing", "viral communication",
            "intercultural communication", "cross cultural communication", "diplomacy communication",
            "information systems", "knowledge management", "information governance",
            "data privacy communication", "freedom of information",
        ]
    },
    "Manajemen Logistik": {
        "concept_id": "C192562407",
        "seeds": [
            "supply chain management", "logistics optimization", "warehouse management", "inventory control",
            "transportation logistics", "freight management", "last mile delivery", "cold chain logistics",
            "reverse logistics", "green logistics", "sustainable supply chain", "circular supply chain",
            "supply chain resilience", "supply chain risk management", "supply chain disruption",
            "procurement strategy", "supplier selection", "supplier relationship management",
            "demand forecasting", "demand planning", "sales operations planning",
            "lean logistics", "agile supply chain", "just in time logistics",
            "blockchain supply chain", "IoT supply chain", "AI supply chain",
            "digital twin logistics", "autonomous vehicles logistics", "drone delivery",
            "cross docking", "distribution network design", "facility location optimization",
            "vehicle routing problem", "fleet management", "route optimization",
            "port logistics", "maritime logistics", "intermodal transportation",
            "e-commerce logistics", "omnichannel logistics", "fulfillment center operations",
            "humanitarian logistics", "disaster relief logistics", "military logistics",
            "food supply chain", "pharmaceutical logistics", "hazardous materials logistics",
            "supply chain finance", "trade finance logistics",
        ]
    },
    "Ekonomi": {
        "concept_id": "C161191863",
        "seeds": [
            "macroeconomics", "microeconomics", "monetary policy", "fiscal policy",
            "inflation targeting", "interest rate policy", "exchange rate dynamics",
            "economic growth", "GDP forecasting", "business cycle", "economic recession",
            "labor economics", "wage inequality", "unemployment dynamics", "labor market flexibility",
            "development economics", "poverty reduction", "economic inequality", "Gini coefficient",
            "international trade", "trade policy", "tariffs", "free trade agreements",
            "financial markets", "stock market", "bond market", "foreign exchange market",
            "banking", "financial regulation", "Basel III", "systemic risk",
            "behavioral economics", "nudge theory", "prospect theory", "bounded rationality",
            "environmental economics", "carbon pricing", "green economy", "sustainable development",
            "digital economy", "platform economy", "gig economy", "cryptocurrency economics",
            "health economics", "pharmaceutical economics", "insurance markets",
            "agricultural economics", "food economics", "commodity markets",
            "urban economics", "regional economics", "spatial economics",
            "public economics", "tax policy", "government spending", "public debt",
            "innovation economics", "knowledge economy", "technology transfer",
            "Islamic economics", "Shariah finance", "sukuk market",
        ]
    },
    "Teknik Mesin": {
        "concept_id": "C192562407",
        "seeds": [
            "thermodynamics", "heat transfer", "fluid mechanics", "computational fluid dynamics",
            "combustion engineering", "internal combustion engine", "gas turbine", "steam turbine",
            "renewable energy systems", "solar thermal", "geothermal energy", "biomass energy",
            "HVAC systems", "refrigeration", "air conditioning", "thermal comfort",
            "mechanical design", "finite element analysis", "stress analysis", "fatigue analysis",
            "vibration analysis", "rotor dynamics", "noise control", "acoustics",
            "manufacturing processes", "CNC machining", "additive manufacturing", "3D printing metal",
            "welding technology", "casting", "forging", "sheet metal forming",
            "robotics", "mechatronics", "automation systems", "industrial robots",
            "tribology", "lubrication", "wear analysis", "surface engineering",
            "automotive engineering", "vehicle dynamics", "aerodynamics", "wind tunnel testing",
            "power generation", "combined cycle", "cogeneration", "energy efficiency",
            "nanotechnology", "nanofluids", "microfluidics", "MEMS devices",
            "composite materials", "smart materials", "shape memory alloys",
        ]
    },
    "Teknik Listrik": {
        "concept_id": "C192562407",
        "seeds": [
            "power systems", "power generation", "power transmission", "power distribution",
            "smart grid", "microgrid", "renewable energy integration", "grid stability",
            "high voltage engineering", "power electronics", "power quality", "harmonic analysis",
            "electric motor", "induction motor", "synchronous machine", "motor drive",
            "transformer design", "circuit breaker", "protection relay", "fault analysis",
            "solar photovoltaic", "wind energy conversion", "energy storage systems", "battery management",
            "electric vehicle", "EV charging infrastructure", "wireless power transfer",
            "power system optimization", "load forecasting", "demand response",
            "SCADA systems", "substation automation", "distribution automation",
            "FACTS devices", "HVDC transmission", "flexible AC transmission",
            "lightning protection", "grounding systems", "electromagnetic compatibility",
            "electrical safety", "arc flash analysis", "insulation coordination",
            "digital signal processing", "power system communication", "IoT power systems",
            "energy management", "building automation", "industrial automation",
            "control systems", "PLC programming", "supervisory control",
        ]
    },
    "Teknik Sipil": {
        "concept_id": "C192562407",
        "seeds": [
            "structural engineering", "reinforced concrete", "prestressed concrete", "steel structures",
            "earthquake engineering", "seismic design", "base isolation", "structural health monitoring",
            "geotechnical engineering", "soil mechanics", "foundation engineering", "slope stability",
            "transportation engineering", "highway design", "pavement engineering", "traffic engineering",
            "bridge engineering", "tunnel engineering", "dam engineering", "retaining walls",
            "construction management", "project management", "BIM building information modeling",
            "sustainable construction", "green building", "LEED certification",
            "concrete technology", "high performance concrete", "self healing concrete", "recycled aggregate",
            "water resources engineering", "hydrology", "flood management", "stormwater management",
            "environmental engineering", "water treatment", "wastewater treatment", "solid waste management",
            "coastal engineering", "port engineering", "offshore structures",
            "wind engineering", "tall buildings", "composite structures",
            "urban infrastructure", "smart infrastructure", "resilient infrastructure",
            "construction safety", "construction productivity", "lean construction",
            "finite element method structures", "structural optimization",
        ]
    },
    "Arsitektur": {
        "concept_id": "C169386139",
        "seeds": [
            "architectural design", "sustainable architecture", "green architecture", "passive design",
            "parametric design", "computational architecture", "generative design", "digital fabrication",
            "vernacular architecture", "traditional architecture", "cultural heritage conservation",
            "urban design", "public space design", "placemaking", "walkable cities",
            "housing design", "affordable housing", "social housing", "modular housing",
            "interior architecture", "adaptive reuse", "building renovation",
            "landscape architecture", "urban landscape", "ecological design",
            "tropical architecture", "bioclimatic design", "natural ventilation",
            "architectural theory", "phenomenology architecture", "critical regionalism",
            "BIM architecture", "virtual reality architecture", "augmented reality design",
            "healthcare architecture", "hospital design", "healing environment",
            "educational architecture", "school design", "campus planning",
            "religious architecture", "mosque architecture", "sacred space design",
            "high rise architecture", "skyscraper design", "mixed use development",
            "disaster resilient architecture", "post disaster reconstruction",
            "architectural history", "modern architecture", "contemporary architecture",
        ]
    },
    "Perkapalan": {
        "concept_id": "C192562407",
        "seeds": [
            "naval architecture", "ship design", "ship hydrodynamics", "ship resistance",
            "ship propulsion", "marine engine", "diesel engine marine", "LNG propulsion",
            "ship structural analysis", "ship strength", "fatigue ship structure", "corrosion marine",
            "ship stability", "intact stability", "damage stability", "load line",
            "shipbuilding", "ship production", "shipyard management", "block construction",
            "marine materials", "composite hull", "aluminum ship", "steel ship",
            "offshore engineering", "floating production", "FPSO", "subsea systems",
            "marine renewable energy", "wave energy", "tidal energy", "offshore wind",
            "ship automation", "autonomous ship", "unmanned vessel", "smart ship",
            "ballast water management", "ship emission control", "scrubber system",
            "port operations", "container terminal", "ship scheduling",
            "fisheries vessel", "fishing boat design", "aquaculture vessel",
            "passenger ship", "ferry design", "cruise ship",
            "ship repair", "dry docking", "marine survey",
            "maritime safety", "SOLAS compliance", "maritime regulation",
        ]
    },
    "Perencanaan Wilayah dan Kota": {
        "concept_id": "C39432304",
        "seeds": [
            "urban planning", "regional planning", "spatial planning", "land use planning",
            "smart city", "digital city", "sustainable city", "resilient city",
            "transportation planning", "transit oriented development", "public transport",
            "urban sprawl", "urban growth boundary", "compact city", "new urbanism",
            "housing policy", "slum upgrading", "urban regeneration", "gentrification",
            "urban economics", "real estate development", "property market",
            "urban ecology", "green infrastructure", "urban biodiversity",
            "disaster risk reduction", "flood risk planning", "earthquake preparedness",
            "participatory planning", "community engagement", "bottom up planning",
            "GIS planning", "spatial analysis", "remote sensing urban",
            "urban heat island", "climate adaptation planning", "urban climate",
            "water sensitive urban design", "sponge city", "blue green infrastructure",
            "heritage conservation", "historic district", "cultural landscape",
            "industrial zone planning", "economic zone", "special economic zone",
            "rural development", "village planning", "rural urban linkage",
            "urban governance", "decentralization planning", "metropolitan governance",
        ]
    },
    "Lingkungan": {
        "concept_id": "C39432304",
        "seeds": [
            "climate change", "global warming", "carbon emission", "greenhouse gas",
            "biodiversity conservation", "ecosystem services", "habitat restoration",
            "air pollution", "water pollution", "soil contamination", "noise pollution",
            "waste management", "circular economy", "zero waste", "plastic pollution",
            "environmental impact assessment", "strategic environmental assessment",
            "renewable energy", "energy transition", "net zero emission",
            "water resources", "water scarcity", "groundwater management", "watershed management",
            "deforestation", "reforestation", "forest conservation", "peatland restoration",
            "marine conservation", "coral reef protection", "mangrove restoration",
            "environmental policy", "environmental law", "environmental governance",
            "sustainable agriculture", "organic farming", "agroecology",
            "environmental monitoring", "remote sensing environment", "air quality monitoring",
            "ecotoxicology", "environmental health", "pollution control",
            "carbon capture", "carbon sequestration", "nature based solutions",
            "environmental education", "sustainability literacy", "eco labeling",
            "urban environment", "industrial ecology", "life cycle assessment",
        ]
    },
    "Kelautan": {
        "concept_id": "C86803240",
        "seeds": [
            "oceanography", "physical oceanography", "chemical oceanography", "biological oceanography",
            "marine biology", "marine ecology", "marine biodiversity", "deep sea biology",
            "coral reef ecology", "mangrove ecosystem", "seagrass ecosystem",
            "ocean acidification", "sea level rise", "ocean warming", "marine heatwave",
            "marine pollution", "microplastics ocean", "oil spill", "marine debris",
            "fisheries science", "fish stock assessment", "sustainable fisheries", "aquaculture",
            "marine biotechnology", "marine natural products", "bioactive compounds marine",
            "ocean energy", "wave energy", "tidal energy", "ocean thermal energy",
            "marine spatial planning", "ocean governance", "law of the sea",
            "coastal management", "integrated coastal zone management", "coastal erosion",
            "marine remote sensing", "ocean observation", "underwater acoustics",
            "marine geology", "seafloor mapping", "marine geophysics",
            "marine protected area", "no take zone", "marine conservation",
            "ocean circulation", "ocean currents", "upwelling", "ocean fronts",
            "marine climate", "ENSO El Nino", "Indian Ocean Dipole",
        ]
    },
    "Perikanan": {
        "concept_id": "C86803240",
        "seeds": [
            "aquaculture", "fish farming", "shrimp farming", "seaweed farming",
            "fish nutrition", "fish feed", "probiotics aquaculture", "immunostimulant fish",
            "fish disease", "fish pathology", "vaccine fish", "antimicrobial resistance aquaculture",
            "fish genetics", "fish breeding", "selective breeding aquaculture", "genomic selection fish",
            "fisheries management", "fish stock assessment", "maximum sustainable yield",
            "capture fisheries", "fishing gear", "fishing vessel", "IUU fishing",
            "fish processing", "fish preservation", "cold chain fisheries", "fish quality",
            "sustainable aquaculture", "recirculating aquaculture system", "biofloc technology",
            "integrated multi trophic aquaculture", "aquaponics", "rice fish farming",
            "fisheries economics", "aquaculture business", "seafood trade", "seafood certification",
            "marine protected area fisheries", "community based fisheries", "small scale fisheries",
            "climate change fisheries", "ocean acidification fisheries",
            "fish behavior", "fish physiology", "fish reproduction",
            "seafood safety", "seafood traceability", "blockchain seafood",
            "ornamental fish", "aquarium trade", "coral reef fish",
        ]
    },
    "Psikologi": {
        "concept_id": "C15744967",
        "seeds": [
            "clinical psychology", "cognitive behavioral therapy", "psychotherapy", "trauma therapy",
            "developmental psychology", "child development", "adolescent psychology", "aging psychology",
            "social psychology", "group dynamics", "prejudice", "prosocial behavior",
            "cognitive psychology", "memory", "attention", "decision making",
            "neuropsychology", "brain injury", "cognitive rehabilitation", "executive function",
            "organizational psychology", "workplace well being", "job satisfaction", "burnout",
            "health psychology", "stress management", "coping strategies", "resilience",
            "educational psychology", "learning motivation", "academic achievement", "test anxiety",
            "positive psychology", "happiness", "life satisfaction", "character strengths",
            "forensic psychology", "criminal behavior", "eyewitness testimony", "risk assessment",
            "sports psychology", "performance anxiety", "mental toughness", "flow state",
            "cultural psychology", "acculturation", "collectivism individualism",
            "addiction psychology", "substance abuse", "gambling addiction", "internet addiction",
            "personality psychology", "Big Five personality", "dark triad",
        ]
    },
    "Kimia": {
        "concept_id": "C185592680",
        "seeds": [
            "organic chemistry", "organic synthesis", "C-H activation", "cross coupling reactions",
            "inorganic chemistry", "coordination chemistry", "organometallic chemistry",
            "physical chemistry", "chemical kinetics", "thermochemistry", "electrochemistry",
            "analytical chemistry", "spectroscopy", "chromatography", "mass spectrometry",
            "polymer chemistry", "conducting polymers", "biodegradable polymers",
            "catalysis", "photocatalysis", "electrocatalysis", "enzyme catalysis",
            "green chemistry", "sustainable chemistry", "solvent free reactions",
            "nanochemistry", "nanoparticles", "quantum dots", "nanocomposites",
            "medicinal chemistry", "drug design", "structure activity relationship",
            "computational chemistry", "molecular dynamics", "density functional theory",
            "materials chemistry", "metal organic frameworks", "perovskite materials",
            "battery chemistry", "lithium ion battery", "solid state battery", "supercapacitor",
            "food chemistry", "natural products", "essential oils", "antioxidants",
            "environmental chemistry", "water treatment chemistry", "advanced oxidation",
            "surface chemistry", "colloid science", "self assembly",
            "biochemistry", "protein chemistry", "enzyme engineering",
        ]
    },
    "Teknik Industri": {
        "concept_id": "C192562407",
        "seeds": [
            "operations research", "optimization", "linear programming", "integer programming",
            "production planning", "scheduling", "capacity planning", "aggregate planning",
            "quality management", "Six Sigma", "statistical process control", "total quality management",
            "lean manufacturing", "Toyota production system", "kaizen", "value stream mapping",
            "ergonomics", "human factors", "workplace design", "occupational safety",
            "supply chain management", "inventory management", "warehouse optimization",
            "facility layout", "material handling", "plant design",
            "simulation", "discrete event simulation", "Monte Carlo simulation", "agent based simulation",
            "data analytics", "predictive analytics", "machine learning manufacturing",
            "Industry 4.0", "smart manufacturing", "digital twin", "cyber physical systems",
            "product design", "design for manufacturing", "design for assembly",
            "project management", "agile project management", "critical path method",
            "reliability engineering", "maintenance optimization", "predictive maintenance",
            "human resource management", "workforce planning", "performance management",
            "sustainability manufacturing", "circular economy manufacturing", "green manufacturing",
        ]
    },
    "Otomasi": {
        "concept_id": "C41008148",
        "seeds": [
            "industrial automation", "PLC programming", "SCADA systems", "DCS distributed control",
            "process automation", "batch process control", "continuous process control",
            "robotics", "industrial robot", "collaborative robot", "robot programming",
            "machine vision", "image processing", "pattern recognition", "deep learning vision",
            "sensor technology", "IoT sensors", "wireless sensor network",
            "control systems", "PID control", "model predictive control", "adaptive control",
            "artificial intelligence automation", "machine learning control", "reinforcement learning control",
            "autonomous systems", "autonomous vehicle", "autonomous drone", "autonomous robot",
            "digital twin", "virtual commissioning", "simulation automation",
            "smart factory", "Industry 4.0", "cyber physical systems",
            "motion control", "servo drive", "stepper motor", "linear actuator",
            "pneumatic systems", "hydraulic systems", "electromechanical systems",
            "building automation", "home automation", "smart building",
            "network security automation", "OT security", "industrial cybersecurity",
            "human machine interface", "operator training", "augmented reality maintenance",
        ]
    },
    "Otomotif": {
        "concept_id": "C192562407",
        "seeds": [
            "electric vehicle", "hybrid vehicle", "fuel cell vehicle", "battery electric vehicle",
            "automotive engine", "internal combustion engine", "turbocharger", "engine efficiency",
            "automotive transmission", "CVT", "dual clutch transmission", "automatic transmission",
            "vehicle dynamics", "suspension system", "brake system", "steering system",
            "autonomous driving", "ADAS", "lane keeping assist", "adaptive cruise control",
            "vehicle aerodynamics", "drag reduction", "downforce optimization",
            "automotive materials", "lightweight materials", "carbon fiber automotive", "aluminum body",
            "automotive electronics", "ECU", "CAN bus", "vehicle to everything V2X",
            "connected vehicle", "telematics", "over the air update",
            "automotive manufacturing", "assembly line", "robotic welding", "paint shop",
            "automotive safety", "crashworthiness", "airbag system", "pedestrian protection",
            "automotive NVH", "noise vibration harshness", "acoustic comfort",
            "automotive emissions", "emission control", "aftertreatment system", "Euro 7 standard",
            "automotive aftermarket", "vehicle maintenance", "diagnostic systems",
        ]
    },
    "Bahasa Asing": {
        "concept_id": "C76002411",
        "seeds": [
            "second language acquisition", "foreign language teaching", "language pedagogy",
            "communicative language teaching", "task based language teaching", "content based instruction",
            "English for specific purposes", "English for academic purposes", "business English",
            "translation studies", "machine translation", "literary translation", "localization",
            "interpreting studies", "simultaneous interpreting", "consecutive interpreting",
            "applied linguistics", "language testing", "language assessment", "proficiency testing",
            "bilingualism", "multilingualism", "code switching", "translanguaging",
            "discourse analysis", "critical discourse analysis", "genre analysis",
            "corpus linguistics", "lexical analysis", "collocation studies",
            "pragmatics", "speech act theory", "politeness theory", "implicature",
            "sociolinguistics", "language ideology", "language policy", "language planning",
            "computational linguistics", "natural language processing", "sentiment analysis",
            "contrastive analysis", "error analysis", "interlanguage",
            "language learning technology", "CALL computer assisted", "mobile learning language",
            "vocabulary acquisition", "reading comprehension", "writing instruction",
        ]
    },
    "Teknologi Pangan": {
        "concept_id": "C86803240",
        "seeds": [
            "food safety", "food microbiology", "foodborne pathogens", "HACCP",
            "food processing", "thermal processing", "non thermal processing", "high pressure processing",
            "food preservation", "drying technology", "freeze drying", "modified atmosphere packaging",
            "food fermentation", "probiotics", "prebiotics", "synbiotics",
            "functional food", "nutraceuticals", "bioactive compounds", "antioxidant food",
            "food chemistry", "Maillard reaction", "lipid oxidation", "food emulsion",
            "food packaging", "active packaging", "intelligent packaging", "biodegradable packaging",
            "food quality", "sensory evaluation", "texture analysis", "color measurement",
            "food engineering", "extrusion technology", "membrane filtration", "ultrasound food",
            "plant based food", "meat analog", "dairy alternative", "insect protein",
            "food waste", "food loss reduction", "upcycling food waste",
            "traditional food", "indigenous food", "ethnic food",
            "food regulation", "food labeling", "food traceability", "blockchain food",
            "nutrigenomics", "personalized nutrition", "dietary fiber",
        ]
    },
    "Farmasi": {
        "concept_id": "C71924100",
        "seeds": [
            "drug discovery", "drug design", "structure based drug design", "virtual screening",
            "pharmaceutical formulation", "tablet formulation", "nanoparticle drug delivery", "liposome",
            "pharmacokinetics", "pharmacodynamics", "drug metabolism", "bioavailability",
            "clinical pharmacy", "medication therapy management", "pharmaceutical care",
            "natural product pharmacy", "herbal medicine", "phytochemistry", "traditional medicine",
            "biopharmaceutics", "biologics", "biosimilars", "monoclonal antibody",
            "drug delivery systems", "targeted delivery", "controlled release", "transdermal delivery",
            "pharmaceutical analysis", "HPLC", "LC-MS", "method validation",
            "pharmacovigilance", "adverse drug reaction", "drug safety",
            "pharmaceutical technology", "continuous manufacturing", "quality by design",
            "regulatory affairs", "drug approval", "bioequivalence",
            "pharmaceutical marketing", "pharmacy management", "community pharmacy",
            "antimicrobial resistance", "antibiotic stewardship", "antiviral drugs",
            "cancer pharmacology", "chemotherapy", "immunotherapy drugs",
            "pharmacogenomics", "precision medicine", "personalized therapy",
        ]
    },
    "Kesehatan": {
        "concept_id": "C71924100",
        "seeds": [
            "public health", "epidemiology", "disease surveillance", "pandemic preparedness",
            "health policy", "healthcare financing", "universal health coverage", "health insurance",
            "primary healthcare", "community health", "rural health", "telemedicine",
            "maternal health", "child health", "neonatal health", "reproductive health",
            "infectious diseases", "tuberculosis", "HIV AIDS", "malaria", "dengue",
            "non communicable diseases", "diabetes", "hypertension", "cardiovascular disease",
            "mental health", "depression", "anxiety disorder", "suicide prevention",
            "nutrition", "malnutrition", "obesity", "stunting",
            "health promotion", "health education", "health literacy", "behavior change",
            "environmental health", "occupational health", "workplace safety",
            "health informatics", "electronic health records", "health data analytics",
            "global health", "health equity", "social determinants health",
            "aging health", "geriatric care", "palliative care",
            "emergency medicine", "disaster health", "trauma care",
            "healthcare quality", "patient safety", "clinical governance",
        ]
    },
    "Biologi": {
        "concept_id": "C86803240",
        "seeds": [
            "molecular biology", "gene expression", "PCR", "CRISPR gene editing",
            "cell biology", "cell signaling", "apoptosis", "cell cycle",
            "genetics", "genomics", "epigenetics", "population genetics",
            "microbiology", "bacteriology", "virology", "mycology",
            "ecology", "biodiversity", "conservation biology", "ecosystem ecology",
            "evolutionary biology", "phylogenetics", "speciation", "molecular evolution",
            "plant biology", "photosynthesis", "plant physiology", "plant breeding",
            "zoology", "animal behavior", "ethology", "wildlife biology",
            "bioinformatics", "computational biology", "systems biology", "multi omics",
            "biotechnology", "synthetic biology", "metabolic engineering", "bioprocess",
            "neuroscience", "neurobiology", "neuroplasticity", "neurodegeneration",
            "developmental biology", "stem cells", "tissue engineering", "regenerative biology",
            "marine biology", "coral biology", "deep sea biology",
            "entomology", "pollinator biology", "insect ecology",
        ]
    },
    "Fisika": {
        "concept_id": "C121332964",
        "seeds": [
            "quantum mechanics", "quantum computing", "quantum entanglement", "quantum cryptography",
            "condensed matter physics", "superconductivity", "topological insulators", "semiconductor physics",
            "particle physics", "Higgs boson", "neutrino physics", "dark matter",
            "astrophysics", "cosmology", "gravitational waves", "black holes",
            "nuclear physics", "nuclear fusion", "nuclear fission", "radioactivity",
            "optics", "photonics", "laser physics", "nonlinear optics",
            "plasma physics", "fusion plasma", "magnetohydrodynamics",
            "statistical mechanics", "thermodynamics", "non equilibrium physics",
            "fluid dynamics", "turbulence", "microfluidics", "rheology",
            "materials physics", "nanomaterials", "2D materials", "metamaterials",
            "biophysics", "protein folding", "molecular dynamics simulation",
            "medical physics", "radiation therapy", "medical imaging", "MRI physics",
            "geophysics", "seismology", "atmospheric physics", "climate physics",
            "acoustics", "ultrasound", "sonic crystal",
        ]
    },
}


def expand_topics_fast(field_name: str, seeds: list[str], target: int = 100) -> list[dict]:
    """Get topics from seeds + OpenAlex subconcept expansion."""
    topics = []
    seen = set()

    # Add seeds directly
    for seed in seeds:
        if seed.lower() not in seen:
            topics.append({"field": field_name, "topic": seed})
            seen.add(seed.lower())

    # Expand via subconcepts
    concept_id = FIELDS_TOPICS.get(field_name, {}).get("concept_id")
    if concept_id and len(topics) < target:
        try:
            r = requests.get(
                f"https://api.openalex.org/concepts/{concept_id}/subconcepts",
                params={"sort": "works_count:desc", "per_page": 200, "mailto": "research@example.com"},
                timeout=15)
            if r.status_code == 200:
                for item in r.json().get("results", []):
                    name = item.get("display_name", "")
                    if name.lower() not in seen and len(topics) < target:
                        topics.append({"field": field_name, "topic": name})
                        seen.add(name.lower())
        except Exception as e:
            print(f"  ⚠️  Expansion failed for {field_name}: {e}")
        time.sleep(0.5)

    return topics[:target]


def generate_all(topics_per_field: int = 100) -> list[dict]:
    all_topics = []
    for field_name, config in FIELDS_TOPICS.items():
        print(f"\n📚 {field_name}")
        topics = expand_topics_fast(field_name, config["seeds"], topics_per_field)
        print(f"  → {len(topics)} topics")
        if topics:
            print(f"    Top 3: {', '.join(t['topic'] for t in topics[:3])}")
        all_topics.extend(topics)
        time.sleep(0.5)
    return all_topics


def save_to_db(topics: list[dict], target_per_topic: int = 10000):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    inserted = 0
    for t in topics:
        try:
            cur.execute("""
                INSERT INTO mega_fetch_progress (field_name, topic, target_count, status)
                VALUES (%s, %s, %s, 'pending')
                ON CONFLICT (field_name, topic) DO NOTHING
            """, (t["field"], t["topic"], target_per_topic))
            if cur.rowcount > 0:
                inserted += 1
        except Exception:
            conn.rollback()
    conn.commit()
    cur.close()
    conn.close()
    return inserted


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    print(f"🚀 MEGA TOPIC GENERATOR V3")
    print(f"   Bidang: {len(FIELDS_TOPICS)}")
    print(f"   Topik/bidang: {n}")
    print(f"   Target/topik: {target:,} papers")
    print(f"   Grand total: {len(FIELDS_TOPICS) * n * target:,} papers\n")

    topics = generate_all(n)
    print(f"\n📊 Generated: {len(topics)} topics")

    # Save JSON
    json_path = "/media/sirobo/Data/PaperDatabase/mega_topics_v3.json"
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(topics, f, indent=2)
    print(f"💾 JSON: {json_path}")

    # Save to DB
    inserted = save_to_db(topics, target)
    print(f"💾 DB: {inserted} topics inserted (target {target:,}/topik)")

    from collections import Counter
    field_counts = Counter(t["field"] for t in topics)
    print(f"\n📊 Per bidang:")
    for field, count in sorted(field_counts.items()):
        print(f"   {field}: {count} topik → {count * target:,} papers")
