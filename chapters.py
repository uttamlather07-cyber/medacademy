"""
chapters.py
Standard NEET syllabus chapter list, organized by subject.

Used to populate topic dropdowns (quiz generation) and the PDF library
(subject -> chapter navigation), so both features stay in sync with the
same canonical list instead of free-typed, typo-prone topic strings.

NEET treats Biology as two papers (Botany + Zoology) even though students
often just say "Biology" - we keep them separate here since that matches
how NEET question papers and most coaching materials are structured.
"""

NEET_CHAPTERS = {
    "Physics": [
        "Physical World and Measurement",
        "Kinematics",
        "Laws of Motion",
        "Work, Energy and Power",
        "Motion of System of Particles and Rigid Body",
        "Gravitation",
        "Mechanical Properties of Solids",
        "Mechanical Properties of Fluids",
        "Thermal Properties of Matter",
        "Thermodynamics",
        "Kinetic Theory of Gases",
        "Oscillations",
        "Waves",
        "Electrostatics",
        "Current Electricity",
        "Moving Charges and Magnetism",
        "Magnetism and Matter",
        "Electromagnetic Induction",
        "Alternating Current",
        "Electromagnetic Waves",
        "Ray Optics and Optical Instruments",
        "Wave Optics",
        "Dual Nature of Radiation and Matter",
        "Atoms",
        "Nuclei",
        "Semiconductor Electronics",
        "Experimental Skills",
    ],
    "Chemistry": [
        "Some Basic Concepts of Chemistry",
        "Structure of Atom",
        "Classification of Elements and Periodicity",
        "Chemical Bonding and Molecular Structure",
        "States of Matter",
        "Thermodynamics",
        "Equilibrium",
        "Redox Reactions",
        "Hydrogen",
        "s-Block Elements",
        "p-Block Elements (Group 13 and 14)",
        "Organic Chemistry - Basic Principles and Techniques",
        "Hydrocarbons",
        "Environmental Chemistry",
        "Solid State",
        "Solutions",
        "Electrochemistry",
        "Chemical Kinetics",
        "Surface Chemistry",
        "General Principles and Processes of Isolation of Elements",
        "p-Block Elements (Group 15 to 18)",
        "d and f Block Elements",
        "Coordination Compounds",
        "Haloalkanes and Haloarenes",
        "Alcohols, Phenols and Ethers",
        "Aldehydes, Ketones and Carboxylic Acids",
        "Organic Compounds Containing Nitrogen",
        "Biomolecules",
        "Polymers",
        "Chemistry in Everyday Life",
    ],
    "Botany": [
        "The Living World",
        "Biological Classification",
        "Plant Kingdom",
        "Morphology of Flowering Plants",
        "Anatomy of Flowering Plants",
        "Cell: The Unit of Life",
        "Cell Cycle and Cell Division",
        "Photosynthesis in Higher Plants",
        "Respiration in Plants",
        "Plant Growth and Development",
        "Sexual Reproduction in Flowering Plants",
        "Principles of Inheritance and Variation",
        "Molecular Basis of Inheritance",
        "Microbes in Human Welfare",
        "Biotechnology: Principles and Processes",
        "Biotechnology and its Applications",
        "Organisms and Populations",
        "Ecosystem",
        "Biodiversity and Conservation",
    ],
    "Zoology": [
        "Animal Kingdom",
        "Structural Organisation in Animals",
        "Breathing and Exchange of Gases",
        "Body Fluids and Circulation",
        "Excretory Products and their Elimination",
        "Locomotion and Movement",
        "Neural Control and Coordination",
        "Chemical Coordination and Integration",
        "Human Reproduction",
        "Reproductive Health",
        "Human Health and Disease",
        "Evolution",
        "Digestion and Absorption",
    ],
}

SUBJECTS = list(NEET_CHAPTERS.keys())


def get_chapters(subject: str) -> list:
    """Returns the chapter list for a subject, or an empty list if unknown."""
    return NEET_CHAPTERS.get(subject, [])