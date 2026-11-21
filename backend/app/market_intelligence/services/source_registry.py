import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.market_intelligence.models import MarketSource, ProductCatalog, ProductMatchRule

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Official Solwer Product Portfolio (Verified against https://solwerindia.com/)
# -----------------------------------------------------------------------------
SOLWER_PRODUCTS = [
    {
        "code": "TWMS",
        "name": "TWMS (Transport & Warehouse Management System)",
        "official_url": "https://solwerindia.com/products/transport-warehouse-management/",
        "business_area": "Logistics & Supply Chain",
        "priority": 1,  # Strategic Priority #1
        "is_active": True,
        "aliases": ["Transport and Warehouse Management System", "Solwer TWMS", "Warehouse Management", "Transport Management"],
        "description": "Comprehensive enterprise transport and warehouse management software optimizing inbound/outbound movements, multi-depot storage, picking, dispatch accuracy and freight costs.",
        "features": [
            "Multi-depot warehouse optimization",
            "Real-time dispatch tracking and truck loading",
            "Automated batch and serial number traceability",
            "Cross-docking and dock door scheduling",
            "Bin/rack space utilization analytics",
            "Integrated freight rate and carrier management",
        ],
        "problems_solved": [
            "High warehouse storage and picking labor costs",
            "Dispatch errors and delayed truck turnaround times",
            "Fragmented carrier tracking and logistics blindspots",
            "Inventory inaccuracies and stockouts",
        ],
        "target_industries": [
            "Logistics & 3PL/4PL",
            "Automotive OEMs & Tier 1 Suppliers",
            "Manufacturing & Engineering",
            "Retail & E-commerce Distribution",
            "Cold Chain & FMCG",
        ],
        "target_company_segments": [
            "logistics_fleet",
            "warehouse_operators",
            "distribution_centres",
            "oem",
            "supplier",
        ],
        "potential_buyer_roles": [
            "Chief Logistics Officer",
            "VP Supply Chain",
            "Director of Logistics Operations",
            "Warehouse General Manager",
            "Head of Distribution",
        ],
        "relevant_business_events": [
            "warehouse_expansion",
            "new_distribution_centre",
            "logistics_park",
            "supply_chain_expansion",
            "transportation_contract",
            "logistics_partnership",
            "freight_management_initiatives",
        ],
        "matching_weights": {
            "product_relevance": 35,
            "event_strength": 25,
            "icp_fit": 20,
            "recency": 10,
            "existing_relationship": 10,
        },
        "rules": [
            {
                "rule_name": "Warehouse & Depot Expansion",
                "event_categories": ["warehouse_expansion", "new_distribution_centre", "logistics_park", "supply_chain_expansion"],
                "positive_keywords": ["warehouse", "distribution centre", "fulfilment centre", "depot", "cross dock", "storage capacity", "sq ft", "supply chain hub", "logistics park"],
                "negative_keywords": ["residential", "commercial office space"],
                "industry_filters": ["Logistics", "Transportation", "Automotive", "Manufacturing", "Retail"],
                "weight": 1.2,
            },
            {
                "rule_name": "Transportation & Freight Contracts",
                "event_categories": ["transportation_contract", "logistics_partnership", "freight_procurement"],
                "positive_keywords": ["freight contract", "transport management", "multimodal", "dispatch", "haulage", "cargo movement", "3PL partnership"],
                "negative_keywords": ["passenger flight", "personal travel"],
                "industry_filters": ["Logistics", "Transportation", "Automotive"],
                "weight": 1.1,
            },
        ],
    },
    {
        "code": "LOSS_TRACKER_IM",
        "name": "Loss Tracker / IM (Integrated Manufacturing)",
        "official_url": "https://solwerindia.com/products/loss-tracker/",
        "business_area": "Manufacturing & Plant Operations",
        "priority": 1,  # Strategic Priority #2
        "is_active": True,
        "aliases": ["Integrated Manufacturing", "Solwer IM", "Loss Tracker", "Manufacturing Loss Tracker", "Plant OEE"],
        "description": "Smart factory loss-reduction and Overall Equipment Effectiveness (OEE) tracking solution empowering plants to identify machine micro-stoppages, reduce scrap, and drive continuous KAIZEN improvements.",
        "features": [
            "Real-time machine uptime and downtime root cause tracking",
            "OEE calculation across shifts, lines, and cells",
            "Digital KAIZEN and loss Pareto distribution",
            "Operator anomaly and cycle-time variance alerts",
            "Line maintenance predictive alerts",
            "Quality rejection and scrap rate analytics",
        ],
        "problems_solved": [
            "Unexplained production line bottlenecks and machine downtime",
            "Manual paper-based shift loss logging and inaccurate OEE metrics",
            "High scrap rates and quality deviations in manufacturing",
            "Slow reaction to equipment micro-stoppages",
        ],
        "target_industries": [
            "Automotive OEMs",
            "Automotive Component Manufacturers & Tier 1/2 Suppliers",
            "Heavy Engineering & Precision Machining",
            "Industrial Machinery & Metal Fabrication",
        ],
        "target_company_segments": [
            "oem",
            "supplier",
            "manufacturing_plants",
            "tier_1_suppliers",
            "tier_2_suppliers",
        ],
        "potential_buyer_roles": [
            "VP Manufacturing",
            "Plant Head / Factory Director",
            "Operations Director",
            "Continuous Improvement / KAIZEN Head",
            "Quality Assurance Director",
        ],
        "relevant_business_events": [
            "manufacturing_expansion",
            "new_manufacturing_plant",
            "factory_expansion",
            "production_capacity_expansion",
            "manufacturing_automation",
            "smart_factory",
            "industry_4_0",
            "loss_reduction",
            "quality_improvement",
        ],
        "matching_weights": {
            "product_relevance": 35,
            "event_strength": 25,
            "icp_fit": 20,
            "recency": 10,
            "existing_relationship": 10,
        },
        "rules": [
            {
                "rule_name": "Plant & Production Capacity Expansion",
                "event_categories": ["manufacturing_expansion", "new_manufacturing_plant", "factory_expansion", "production_capacity_expansion"],
                "positive_keywords": ["plant expansion", "new facility", "production line", "manufacturing capacity", "greenfield plant", "assembly line", "factory investment", "crore investment"],
                "negative_keywords": ["store opening", "retail outlet"],
                "industry_filters": ["Automotive", "Manufacturing", "Auto Components", "Engineering"],
                "weight": 1.25,
            },
            {
                "rule_name": "Smart Factory & Automation Initiatives",
                "event_categories": ["manufacturing_automation", "smart_factory", "industry_4_0", "loss_reduction"],
                "positive_keywords": ["industry 4.0", "smart factory", "automation", "oee", "kaizen", "iot", "digital shopfloor", "lean manufacturing", "productivity improvement"],
                "negative_keywords": [],
                "industry_filters": ["Automotive", "Manufacturing", "Suppliers"],
                "weight": 1.15,
            },
        ],
    },
    {
        "code": "VDI",
        "name": "Vehicle Digital Inspection (VDI)",
        "official_url": "https://solwerindia.com/products/vehicle-digital-inspection/",
        "business_area": "Automotive Inspection & Quality Assurance",
        "priority": 2,
        "is_active": True,
        "aliases": ["VDI", "Solwer VDI", "Vehicle Inspection", "Digital Vehicle Inspection"],
        "description": "AI-powered mobile inspection system providing standardized digital condition checklists, automatic scratch/dent detection, and transparent vehicle grading reports.",
        "features": [
            "AI-assisted body scratch and dent recognition",
            "Standardized multi-point digital inspection forms",
            "Tamper-proof photo and timestamped audit logs",
            "Instant commercial vehicle and used car grading report generation",
            "Yard inspection and turnaround time tracking",
        ],
        "problems_solved": [
            "Disputed vehicle damage claims and subjective inspection scoring",
            "Slow, paper-based vehicle intake procedures in yards and workshops",
            "Missed pre-trip or return inspection damage defects",
            "Lack of transparency in used vehicle valuation and refurbishment",
        ],
        "target_industries": [
            "Used Car Platforms & Multi-Brand Dealerships",
            "Commercial Fleet Operators & Trucking",
            "Vehicle Leasing & Rental Companies",
            "Automotive Aftermarket & Service Chains",
            "Vehicle Insurance & Assessment",
        ],
        "target_company_segments": [
            "dealership_aftermarket",
            "used_car_dealerships",
            "fleet_operators",
            "vehicle_inspection_businesses",
        ],
        "potential_buyer_roles": [
            "Dealership Network Head",
            "VP Pre-Owned / Used Car Business",
            "Fleet Operations Director",
            "Workshop General Manager",
            "Chief Claims & Inspection Officer",
        ],
        "relevant_business_events": [
            "dealership_expansion",
            "used_car_expansion",
            "vehicle_inspection_initiative",
            "vehicle_refurbishment",
            "service_network_expansion",
            "dealer_partnerships",
        ],
        "matching_weights": {
            "product_relevance": 30,
            "event_strength": 25,
            "icp_fit": 20,
            "recency": 15,
            "existing_relationship": 10,
        },
        "rules": [
            {
                "rule_name": "Dealership & Used Car Expansion",
                "event_categories": ["dealership_expansion", "used_car_expansion", "vehicle_inspection_initiative"],
                "positive_keywords": ["used car", "pre-owned", "dealership network", "refurbishment centre", "vehicle inspection", "touchpoints", "showroom expansion", "service centres"],
                "negative_keywords": [],
                "industry_filters": ["Dealerships", "Automotive", "Aftermarket"],
                "weight": 1.2,
            },
        ],
    },
    {
        "code": "FLEET_MGMT",
        "name": "Fleet Management",
        "official_url": "https://solwerindia.com/products/fleet-management/",
        "business_area": "Fleet & Mobility",
        "priority": 2,
        "is_active": True,
        "aliases": ["Fleet Management", "Solwer Fleet", "Fleet Digitalization"],
        "description": "Comprehensive fleet digitalization platform managing driver pre/post-trip readiness, vehicle maintenance cycles, driver accountability, and telematics integration.",
        "features": [
            "Driver pre-trip and post-trip mobile inspection checklists",
            "Vehicle cleanliness and road-readiness scoring",
            "Preventative service alerts and maintenance history",
            "Driver behavior tracking and accountability scorecards",
            "Breakdown and towing incident management",
        ],
        "problems_solved": [
            "Unplanned on-road fleet breakdowns and high maintenance costs",
            "Driver negligence in pre-trip safety checks",
            "Lack of centralized fleet maintenance scheduling",
            "Vehicle asset downtime and turnaround delays",
        ],
        "target_industries": [
            "Logistics & Heavy Trucking Fleets",
            "Passenger Transport & Bus Operators",
            "Last-Mile Delivery & Quick Commerce",
            "Corporate Car Rental & Taxi Fleets",
        ],
        "target_company_segments": [
            "fleet_operators",
            "trucking_companies",
            "bus_operators",
            "last_mile_delivery",
        ],
        "potential_buyer_roles": [
            "Fleet Operations VP",
            "Director of Fleet Maintenance",
            "Transport Operations Manager",
            "Chief Operating Officer",
        ],
        "relevant_business_events": [
            "fleet_expansion",
            "fleet_procurement",
            "fleet_digitalization",
            "transport_management_initiatives",
            "commercial_vehicle_orders",
        ],
        "matching_weights": {
            "product_relevance": 30,
            "event_strength": 25,
            "icp_fit": 20,
            "recency": 15,
            "existing_relationship": 10,
        },
        "rules": [
            {
                "rule_name": "Fleet Expansion & Commercial Vehicle Procurement",
                "event_categories": ["fleet_expansion", "fleet_procurement", "fleet_digitalization"],
                "positive_keywords": ["fleet expansion", "trucks added", "commercial vehicles", "ev fleet", "delivery fleet", "electric buses", "telematics", "order for vehicles"],
                "negative_keywords": [],
                "industry_filters": ["Logistics", "Transportation", "Fleet"],
                "weight": 1.2,
            },
        ],
    },
    {
        "code": "MCE",
        "name": "Mobility Aftermarket SuperApp (MCE)",
        "official_url": "https://solwerindia.com/products/mobility-aftermarket-superapp/",
        "business_area": "Automotive Aftermarket & Service Networks",
        "priority": 2,
        "is_active": True,
        "aliases": ["MCE", "Solwer MCE", "Mobility Aftermarket", "Aftermarket SuperApp"],
        "description": "Unified digital ecosystem connecting workshops, spare parts distributors, and vehicle owners for transparent maintenance, rapid spare parts ordering, and repair tracking.",
        "features": [
            "Multi-garage and workshop workflow digitization",
            "Automotive spare parts cataloguing and instant dispatch ordering",
            "Real-time job card creation and labor estimation",
            "Customer repair progress updates and digital invoicing",
        ],
        "problems_solved": [
            "Fragmented and opaque independent workshop networks",
            "Delays in automotive spare parts sourcing and logistics",
            "Low customer trust in service billing and repair turnaround",
        ],
        "target_industries": [
            "Independent Workshop Networks & Multi-Brand Service Chains",
            "Automotive Spare Parts Distributors & Retailers",
            "Authorized Dealership Service Networks",
        ],
        "target_company_segments": [
            "service_centres",
            "repair_shops",
            "aftermarket_businesses",
            "spare_parts_distributors",
        ],
        "potential_buyer_roles": [
            "VP Aftermarket & Customer Service",
            "Service Network Director",
            "Spare Parts Business Head",
        ],
        "relevant_business_events": [
            "service_centre_expansion",
            "aftermarket_expansion",
            "dealer_network_expansion",
            "spare_parts_distribution",
            "vehicle_service_digitalization",
        ],
        "matching_weights": {
            "product_relevance": 30,
            "event_strength": 25,
            "icp_fit": 20,
            "recency": 15,
            "existing_relationship": 10,
        },
        "rules": [
            {
                "rule_name": "Aftermarket & Workshop Network Expansion",
                "event_categories": ["service_centre_expansion", "aftermarket_expansion", "vehicle_service_digitalization"],
                "positive_keywords": ["service network", "workshop chain", "garages", "spare parts", "aftermarket sales", "mechanic network", "service hubs"],
                "negative_keywords": [],
                "industry_filters": ["Aftermarket", "Dealerships", "Automotive"],
                "weight": 1.15,
            },
        ],
    },
    {
        "code": "CARBON_MGMT",
        "name": "Carbon Footprint Management",
        "official_url": "https://solwerindia.com/products/carbon-footprint-management/",
        "business_area": "ESG & Sustainable Mobility",
        "priority": 3,
        "is_active": True,
        "aliases": ["Carbon Management", "Solwer Carbon", "ESG Carbon Footprint", "Green Logistics"],
        "description": "Enterprise carbon accounting and emission management software tracking Scope 1, 2, and 3 emissions across transportation routes, factories, and supply chains.",
        "features": [
            "Automated Scope 1, 2, and 3 logistics emissions calculation",
            "Green routing and low-emission carrier allocation",
            "ESG audit and compliance reporting for SEBI BRSR and international standards",
            "Fleet decarbonization pathway modeling",
        ],
        "problems_solved": [
            "Complex and error-prone manual freight emissions calculations",
            "Regulatory compliance penalties for ESG disclosure mandates",
            "Lack of visibility into third-party supply chain Scope 3 emissions",
        ],
        "target_industries": [
            "Large Logistics & Freight Forwarding Enterprises",
            "Automotive OEMs & Global Component Exporters",
            "Manufacturing Corporates with Net-Zero Commitments",
        ],
        "target_company_segments": [
            "oem",
            "logistics_fleet",
            "manufacturing_corporates",
        ],
        "potential_buyer_roles": [
            "Chief Sustainability Officer (CSO)",
            "Head of ESG & Compliance",
            "VP Logistics & Green Supply Chain",
        ],
        "relevant_business_events": [
            "carbon_footprint_initiatives",
            "sustainability_programmes",
            "emission_regulations",
            "green_logistics",
            "ev_investments",
        ],
        "matching_weights": {
            "product_relevance": 25,
            "event_strength": 25,
            "icp_fit": 25,
            "recency": 15,
            "existing_relationship": 10,
        },
        "rules": [
            {
                "rule_name": "Decarbonization & Green Logistics Initiatives",
                "event_categories": ["carbon_footprint_initiatives", "sustainability_programmes", "green_logistics", "emission_regulations"],
                "positive_keywords": ["net-zero", "scope 3", "carbon footprint", "emission reduction", "green logistics", "esg", "sustainability report", "brsr"],
                "negative_keywords": [],
                "industry_filters": ["Logistics", "Automotive", "Manufacturing"],
                "weight": 1.1,
            },
        ],
    },
]

# -----------------------------------------------------------------------------
# Initial 62 Monitoring Website Targets (Seeded Registry)
# -----------------------------------------------------------------------------
INITIAL_SOURCES = [
    # A. Indian Automotive Publications (9)
    {"name": "ET Auto", "domain": "auto.economictimes.indiatimes.com", "homepage_url": "https://auto.economictimes.indiatimes.com/", "source_category": "automotive_news", "priority": 1, "crawl_frequency_minutes": 30},
    {"name": "Autocar Professional", "domain": "autocarpro.in", "homepage_url": "https://www.autocarpro.in/", "source_category": "automotive_news", "priority": 1, "crawl_frequency_minutes": 30},
    {"name": "Mobility Outlook", "domain": "mobilityoutlook.com", "homepage_url": "https://www.mobilityoutlook.com/", "source_category": "automotive_news", "priority": 1, "crawl_frequency_minutes": 45},
    {"name": "Autocar India", "domain": "autocarindia.com", "homepage_url": "https://www.autocarindia.com/", "source_category": "automotive_news", "priority": 2, "crawl_frequency_minutes": 60},
    {"name": "MotorIndia", "domain": "motorindiaonline.in", "homepage_url": "https://www.motorindiaonline.in/", "source_category": "automotive_news", "priority": 1, "crawl_frequency_minutes": 45},
    {"name": "CarWale", "domain": "carwale.com", "homepage_url": "https://www.carwale.com/", "source_category": "automotive_news", "priority": 2, "crawl_frequency_minutes": 60},
    {"name": "BikeWale", "domain": "bikewale.com", "homepage_url": "https://www.bikewale.com/", "source_category": "automotive_news", "priority": 2, "crawl_frequency_minutes": 90},
    {"name": "RushLane", "domain": "rushlane.com", "homepage_url": "https://www.rushlane.com/", "source_category": "automotive_news", "priority": 2, "crawl_frequency_minutes": 60},
    {"name": "Overdrive", "domain": "overdrive.in", "homepage_url": "https://www.overdrive.in/", "source_category": "automotive_news", "priority": 2, "crawl_frequency_minutes": 90},

    # B. Automotive Associations and Industry Bodies (7)
    {"name": "SIAM (Society of Indian Automobile Manufacturers)", "domain": "siam.in", "homepage_url": "https://www.siam.in/", "source_category": "association", "priority": 3, "crawl_frequency_minutes": 240},
    {"name": "ACMA (Automotive Component Manufacturers Association)", "domain": "acma.in", "homepage_url": "https://www.acma.in/", "source_category": "association", "priority": 3, "crawl_frequency_minutes": 240},
    {"name": "FADA (Federation of Automobile Dealers Associations)", "domain": "fada.in", "homepage_url": "https://fada.in/", "source_category": "association", "priority": 3, "crawl_frequency_minutes": 240},
    {"name": "ARAI (Automotive Research Association of India)", "domain": "araiindia.com", "homepage_url": "https://www.araiindia.com/", "source_category": "association", "priority": 4, "crawl_frequency_minutes": 360},
    {"name": "Confederation of Indian Industry (CII)", "domain": "cii.in", "homepage_url": "https://www.cii.in/", "source_category": "association", "priority": 4, "crawl_frequency_minutes": 360},
    {"name": "ASSOCHAM", "domain": "assocham.org", "homepage_url": "https://www.assocham.org/", "source_category": "association", "priority": 4, "crawl_frequency_minutes": 360},
    {"name": "SAEINDIA", "domain": "saeindia.org", "homepage_url": "https://www.saeindia.org/", "source_category": "association", "priority": 4, "crawl_frequency_minutes": 360},

    # C. Government and Official Sources (7)
    {"name": "Press Information Bureau (PIB)", "domain": "pib.gov.in", "homepage_url": "https://www.pib.gov.in/", "source_category": "government", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Ministry of Heavy Industries", "domain": "heavyindustries.gov.in", "homepage_url": "https://heavyindustries.gov.in/", "source_category": "government", "priority": 3, "crawl_frequency_minutes": 240},
    {"name": "Ministry of Road Transport and Highways (MoRTH)", "domain": "morth.gov.in", "homepage_url": "https://morth.gov.in/", "source_category": "government", "priority": 3, "crawl_frequency_minutes": 240},
    {"name": "NHAI (National Highways Authority of India)", "domain": "nhai.gov.in", "homepage_url": "https://nhai.gov.in/", "source_category": "government", "priority": 4, "crawl_frequency_minutes": 360},
    {"name": "Government e-Marketplace (GeM)", "domain": "gem.gov.in", "homepage_url": "https://gem.gov.in/", "source_category": "government", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "Central Public Procurement Portal (CPPP)", "domain": "eprocure.gov.in", "homepage_url": "https://eprocure.gov.in/", "source_category": "government", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "Invest India", "domain": "investindia.gov.in", "homepage_url": "https://www.investindia.gov.in/", "source_category": "government", "priority": 4, "crawl_frequency_minutes": 360},

    # D. Logistics, Transportation and Fleet (10) — CRITICAL FOR TWMS
    {"name": "Indian Transport & Logistics News (ITLN)", "domain": "itln.in", "homepage_url": "https://www.itln.in/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 1, "crawl_frequency_minutes": 30},
    {"name": "Logistics Insider", "domain": "logisticsinsider.in", "homepage_url": "https://www.logisticsinsider.in/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 1, "crawl_frequency_minutes": 30},
    {"name": "Logistics Update Africa", "domain": "logisticsupdateafrica.com", "homepage_url": "https://www.logisticsupdateafrica.com/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "ET Transportation", "domain": "economictimes.indiatimes.com", "homepage_url": "https://economictimes.indiatimes.com/industry/transportation", "source_category": "logistics_fleet", "industry": "logistics", "priority": 1, "crawl_frequency_minutes": 30},
    {"name": "Transport Corporation of India (TCI)", "domain": "tcil.com", "homepage_url": "https://www.tcil.com/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Delhivery", "domain": "delhivery.com", "homepage_url": "https://www.delhivery.com/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Mahindra Logistics", "domain": "mahindralogistics.com", "homepage_url": "https://mahindralogistics.com/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "VRL Logistics", "domain": "vrlgroup.in", "homepage_url": "https://www.vrlgroup.in/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Blue Dart Express", "domain": "bluedart.com", "homepage_url": "https://www.bluedart.com/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "TCI Group", "domain": "tcigroup.com", "homepage_url": "https://www.tcigroup.com/", "source_category": "logistics_fleet", "industry": "logistics", "priority": 3, "crawl_frequency_minutes": 180},

    # E. Automotive OEMs (12)
    {"name": "Tata Motors", "domain": "tatamotors.com", "homepage_url": "https://www.tatamotors.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Mahindra & Mahindra", "domain": "mahindra.com", "homepage_url": "https://www.mahindra.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Maruti Suzuki", "domain": "marutisuzuki.com", "homepage_url": "https://www.marutisuzuki.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Hyundai Motor India", "domain": "hyundai.com", "homepage_url": "https://www.hyundai.com/in/en", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Kia India", "domain": "kia.com", "homepage_url": "https://www.kia.com/in/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Toyota Kirloskar Motor", "domain": "toyotabharat.com", "homepage_url": "https://www.toyotabharat.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Ashok Leyland", "domain": "ashokleyland.com", "homepage_url": "https://www.ashokleyland.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Eicher Motors", "domain": "eichermotors.com", "homepage_url": "https://www.eichermotors.com/", "source_category": "oem", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "TVS Motor Company", "domain": "tvsmotor.com", "homepage_url": "https://www.tvsmotor.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Bajaj Auto", "domain": "bajajauto.com", "homepage_url": "https://www.bajajauto.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Hero MotoCorp", "domain": "heromotocorp.com", "homepage_url": "https://www.heromotocorp.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Ather Energy", "domain": "atherenergy.com", "homepage_url": "https://www.atherenergy.com/", "source_category": "oem", "priority": 2, "crawl_frequency_minutes": 120},

    # F. Automotive Component Manufacturers and Suppliers (8) — CRITICAL FOR IM / LOSS TRACKER
    {"name": "Bosch India", "domain": "bosch.in", "homepage_url": "https://www.bosch.in/", "source_category": "supplier", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Samvardhana Motherson", "domain": "motherson.com", "homepage_url": "https://www.motherson.com/", "source_category": "supplier", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Bharat Forge", "domain": "bharatforge.com", "homepage_url": "https://www.bharatforge.com/", "source_category": "supplier", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Uno Minda", "domain": "unominda.com", "homepage_url": "https://www.unominda.com/", "source_category": "supplier", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Sona Comstar", "domain": "sonacomstar.com", "homepage_url": "https://sonacomstar.com/", "source_category": "supplier", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "Sundram Fasteners", "domain": "sundram.com", "homepage_url": "https://www.sundram.com/", "source_category": "supplier", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "Endurance Technologies", "domain": "endurancegroup.com", "homepage_url": "https://www.endurancegroup.com/", "source_category": "supplier", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "ZF India", "domain": "zf.com", "homepage_url": "https://www.zf.com/", "source_category": "supplier", "priority": 3, "crawl_frequency_minutes": 180},

    # G. Dealership and Automotive Aftermarket (7) — CRITICAL FOR VDI & MCE
    {"name": "CarTrade Tech", "domain": "cartrade.com", "homepage_url": "https://www.cartrade.com/", "source_category": "dealership", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Spinny", "domain": "spinny.com", "homepage_url": "https://www.spinny.com/", "source_category": "dealership", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Cars24", "domain": "cars24.com", "homepage_url": "https://www.cars24.com/", "source_category": "dealership", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "Mahindra First Choice Wheels", "domain": "mahindrafirstchoice.com", "homepage_url": "https://www.mahindrafirstchoice.com/", "source_category": "dealership", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "ACKO Drive", "domain": "acko.com", "homepage_url": "https://www.acko.com/", "source_category": "dealership", "priority": 3, "crawl_frequency_minutes": 180},
    {"name": "GoMechanic", "domain": "gomechanic.in", "homepage_url": "https://gomechanic.in/", "source_category": "dealership", "priority": 2, "crawl_frequency_minutes": 120},
    {"name": "CarDekho", "domain": "cardekho.com", "homepage_url": "https://www.cardekho.com/", "source_category": "dealership", "priority": 2, "crawl_frequency_minutes": 120},

    # H. Global Sources for Future Expansion (2) — initially enabled=False / low priority
    {"name": "Automotive News Global", "domain": "autonews.com", "homepage_url": "https://www.autonews.com/", "source_category": "global", "country": "US", "priority": 5, "crawl_frequency_minutes": 720, "enabled": False},
    {"name": "Reuters Autos and Transportation", "domain": "reuters.com", "homepage_url": "https://www.reuters.com/business/autos-transportation/", "source_category": "global", "country": "US", "priority": 5, "crawl_frequency_minutes": 720, "enabled": False},
]


def seed_product_catalog(session: Session) -> dict[str, int]:
    """Seeds the official Solwer products and their configurable match rules."""
    created_products = 0
    created_rules = 0

    for p_data in SOLWER_PRODUCTS:
        code = p_data["code"]
        existing = session.scalar(select(ProductCatalog).where(ProductCatalog.code == code))
        rules_data = p_data.get("rules", [])

        if not existing:
            product = ProductCatalog(
                code=code,
                name=p_data["name"],
                official_url=p_data["official_url"],
                aliases=p_data.get("aliases", []),
                description=p_data["description"],
                business_area=p_data["business_area"],
                features=p_data.get("features", []),
                problems_solved=p_data.get("problems_solved", []),
                target_industries=p_data.get("target_industries", []),
                target_company_segments=p_data.get("target_company_segments", []),
                potential_buyer_roles=p_data.get("potential_buyer_roles", []),
                relevant_business_events=p_data.get("relevant_business_events", []),
                priority=p_data.get("priority", 2),
                is_active=p_data.get("is_active", True),
                matching_weights=p_data.get("matching_weights", {}),
            )
            session.add(product)
            session.flush()
            created_products += 1

            for r_data in rules_data:
                rule = ProductMatchRule(
                    product_id=product.id,
                    rule_name=r_data["rule_name"],
                    event_categories=r_data.get("event_categories", []),
                    positive_keywords=r_data.get("positive_keywords", []),
                    negative_keywords=r_data.get("negative_keywords", []),
                    industry_filters=r_data.get("industry_filters", []),
                    weight=r_data.get("weight", 1.0),
                    is_active=True,
                )
                session.add(rule)
                created_rules += 1
        else:
            # Sync rules if missing
            existing_rule_names = {r.rule_name for r in existing.rules}
            for r_data in rules_data:
                if r_data["rule_name"] not in existing_rule_names:
                    rule = ProductMatchRule(
                        product_id=existing.id,
                        rule_name=r_data["rule_name"],
                        event_categories=r_data.get("event_categories", []),
                        positive_keywords=r_data.get("positive_keywords", []),
                        negative_keywords=r_data.get("negative_keywords", []),
                        industry_filters=r_data.get("industry_filters", []),
                        weight=r_data.get("weight", 1.0),
                        is_active=True,
                    )
                    session.add(rule)
                    created_rules += 1

    session.commit()
    logger.info("Product catalog seeded: %d new products, %d new rules", created_products, created_rules)
    return {"created_products": created_products, "created_rules": created_rules}


def seed_source_registry(session: Session) -> dict[str, int]:
    """Seeds the 62 initial website monitoring targets into the source registry."""
    created_sources = 0

    for s_data in INITIAL_SOURCES:
        domain = s_data["domain"]
        existing = session.scalar(select(MarketSource).where(MarketSource.domain == domain))
        if not existing:
            source = MarketSource(
                name=s_data["name"],
                domain=domain,
                homepage_url=s_data["homepage_url"],
                source_category=s_data["source_category"],
                industry=s_data.get("industry", "automotive"),
                country=s_data.get("country", "IN"),
                language=s_data.get("language", "en"),
                ingestion_method="PLAYWRIGHT",
                priority=s_data.get("priority", 2),
                crawl_frequency_minutes=s_data.get("crawl_frequency_minutes", 60),
                enabled=s_data.get("enabled", True),
                validation_status="pending",
            )
            session.add(source)
            created_sources += 1

    session.commit()
    logger.info("Source registry seeded: %d new sources", created_sources)
    return {"created_sources": created_sources}
