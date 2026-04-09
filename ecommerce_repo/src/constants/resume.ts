import { Lang } from './translations';

export interface EducationEntry {
  institution: string;
  period: string;
  degree: string;
  title: string;
  highlights: string[];
}

export interface ExperienceEntry {
  company: string;
  role: string;
  period: string;
  location?: string;
  highlights: string[];
}

export interface CertificationEntry {
  provider: string;
  name: string;
  period: string;
}

interface ResumeContent {
  coreSkills: string[];
  education: EducationEntry[];
  experience: ExperienceEntry[];
  certifications: CertificationEntry[];
}

export const PROFILE_META = {
  location: 'Las Hualtatas, Vitacura, Santiago, Chile',
  phone: '(+56 9) 3590 0264',
  email: 'sdiazdelafuente9@gmail.com',
  academicEmail: 'sebastiandiaz@alumnos.uai.cl',
};

export const RESUME_CONTENT: Record<Lang, ResumeContent> = {
  es: {
    coreSkills: [
      'LangGraph Multi-Agent Systems',
      'LLM Orchestration',
      'Structured Output with Pydantic',
      'RAGAS Evaluation Pipelines',
      'Python and RESTful APIs',
      'ETL/ELT para Retail',
      'Docker and Kubernetes',
    ],
    education: [
      {
        institution: 'Universidad Adolfo Ibanez',
        period: '2020 - 2024',
        degree: 'Licenciatura en Ciencias de la Ingenieria',
        title: 'Ingenieria Civil Informatica',
        highlights: [
          'Profesor y Ayudante en Cubo Educativo, impartiendo clases de programacion y comunicando conceptos tecnicos complejos.',
          'Secretario Ejecutivo de la Federacion Universitaria (UAI), gestionando iniciativas de retencion y bienestar estudiantil.',
        ],
      },
    ],
    experience: [
      {
        company: 'Grupo Axo',
        role: 'Data Scientist & Automation Analyst',
        period: 'Enero 2025 - Presente',
        highlights: [
          'Lidero arquitectura de pipelines de datos autonomos para retail internacional, reemplazando analisis manual por decisiones automatizadas.',
          'Desarrollo APIs RESTful asincronas en Python para exponer modelos predictivos en sistemas legacy.',
          'Diseno orquestaciones ETL/ELT para ingesta masiva y analisis en tiempo real.',
        ],
      },
      {
        company: 'Al Diente App',
        role: 'Co-Founder & Full-Stack Developer',
        period: '2025',
        highlights: [
          'Co-cree la plataforma completa de Al Diente, participando en arquitectura de sistemas, backend y frontend.',
          'Implemente mejoras de performance y escalabilidad para soportar crecimiento sostenido de usuarios y operaciones.',
        ],
      },
      {
        company: 'agon.cl',
        role: 'Co-Founder & Full-Stack Developer',
        period: '2026',
        highlights: [
          'Co-cree agon.cl como plataforma web end-to-end, definiendo arquitectura, backend, base de datos, APIs REST y frontend responsive.',
          'Lidere la direccion de producto y UX con enfoque minimalista para entregar una experiencia clara y orientada a conversion.',
        ],
      },
      {
        company: 'Project Orthogonal',
        role: 'AI Agent Engineer',
        period: 'Diciembre 2025 - Presente',
        highlights: [
          'Disene un sistema multi-agente persistente con LangGraph y PostgreSQL para auditorias forenses de facturacion (3-way match).',
          'Implemente Structured Output with Pydantic en modelos LLM, reduciendo la alucinacion en OCR a menos de 1% en produccion.',
          'Desarrolle Headhunter CLI, un agente autonomo de ventas para prospeccion dinamica y redaccion contextual.',
          'Desplegue infraestructura de inferencia containerizada con Docker, preparada para Kubernetes.',
        ],
      },
      {
        company: 'Walmart',
        role: 'Data Analytics Intern',
        period: 'Junio 2024 - Diciembre 2024',
        location: 'Santiago, Chile',
        highlights: [
          'Automatice inteligencia de negocios con SQL avanzado, optimizando tiempos de reporte gerencial en 40%.',
          'Desarrolle scripts de automatizacion agentica con LangChain para flujos criticos de Recursos Humanos.',
        ],
      },
    ],
    certifications: [
      {
        provider: 'LangChain Academy',
        name: 'Introduction to Agent Observability and Evaluations',
        period: '2025 - 2026',
      },
      {
        provider: 'LangChain Academy',
        name: 'Certified in Agentic Architectures with LangGraph',
        period: '2025 - 2026',
      },
      {
        provider: 'DeepLearning.AI',
        name: 'Advanced RAG Systems and Evaluation Driven Development',
        period: '2025 - 2026',
      },
      {
        provider: 'Cloud Native Computing',
        name: 'Deploying Scalable AI Services with Kubernetes',
        period: '2025 - 2026',
      },
    ],
  },
  en: {
    coreSkills: [
      'LangGraph Multi-Agent Systems',
      'LLM Orchestration',
      'Structured Output with Pydantic',
      'RAGAS Evaluation Pipelines',
      'Python and RESTful APIs',
      'ETL/ELT for Retail',
      'Docker and Kubernetes',
    ],
    education: [
      {
        institution: 'Universidad Adolfo Ibanez',
        period: '2020 - 2024',
        degree: 'BSc in Engineering Sciences',
        title: 'Computer Engineering',
        highlights: [
          'Teaching Assistant and Instructor at Cubo Educativo, delivering programming classes and explaining complex technical concepts.',
          'Executive Secretary at the UAI Student Federation, leading retention and student wellbeing initiatives.',
        ],
      },
    ],
    experience: [
      {
        company: 'Grupo Axo',
        role: 'Data Scientist and Automation Analyst',
        period: 'January 2025 - Present',
        highlights: [
          'Lead autonomous data pipeline architecture for international retail, replacing manual analysis with automated decision workflows.',
          'Build asynchronous Python RESTful APIs to expose predictive models in legacy systems.',
          'Design ETL/ELT orchestrations for large-scale ingestion and real-time analysis.',
        ],
      },
      {
        company: 'Al Diente App',
        role: 'Co-Founder & Full-Stack Developer',
        period: '2025',
        highlights: [
          'Co-built the full Al Diente platform, owning system architecture, backend services, and frontend implementation.',
          'Implemented performance and scalability improvements to support sustained user and operational growth.',
        ],
      },
      {
        company: 'agon.cl',
        role: 'Co-Founder & Full-Stack Developer',
        period: '2026',
        highlights: [
          'Co-founded and built agon.cl as an end-to-end web platform, defining architecture, backend, database, REST APIs, and responsive frontend.',
          'Led product direction and UX execution with a minimalist approach focused on clarity and conversion.',
        ],
      },
      {
        company: 'Project Orthogonal',
        role: 'AI Agent Engineer',
        period: 'December 2025 - Present',
        highlights: [
          'Designed a persistent multi-agent system with LangGraph and PostgreSQL for complex 3-way match invoice forensic audits.',
          'Implemented strict Structured Output with Pydantic for LLMs, reducing OCR hallucination rates to below 1% in production.',
          'Built Headhunter CLI, an autonomous sales agent for dynamic prospecting and contextual copy generation.',
          'Deployed containerized inference infrastructure with Docker, ready for Kubernetes orchestration.',
        ],
      },
      {
        company: 'Walmart',
        role: 'Data Analytics Intern',
        period: 'June 2024 - December 2024',
        location: 'Santiago, Chile',
        highlights: [
          'Automated business intelligence pipelines with advanced SQL, reducing management reporting times by 40%.',
          'Developed agentic automation scripts with LangChain for critical HR workflows.',
        ],
      },
    ],
    certifications: [
      {
        provider: 'LangChain Academy',
        name: 'Introduction to Agent Observability and Evaluations',
        period: '2025 - 2026',
      },
      {
        provider: 'LangChain Academy',
        name: 'Certified in Agentic Architectures with LangGraph',
        period: '2025 - 2026',
      },
      {
        provider: 'DeepLearning.AI',
        name: 'Advanced RAG Systems and Evaluation Driven Development',
        period: '2025 - 2026',
      },
      {
        provider: 'Cloud Native Computing',
        name: 'Deploying Scalable AI Services with Kubernetes',
        period: '2025 - 2026',
      },
    ],
  },
  de: {
    coreSkills: [
      'LangGraph Multi-Agent Systems',
      'LLM Orchestration',
      'Structured Output with Pydantic',
      'RAGAS Evaluation Pipelines',
      'Python and RESTful APIs',
      'ETL/ELT fuer Retail',
      'Docker and Kubernetes',
    ],
    education: [
      {
        institution: 'Universidad Adolfo Ibanez',
        period: '2020 - 2024',
        degree: 'Bachelor in Ingenieurwissenschaften',
        title: 'Informatikingenieurwesen',
        highlights: [
          'Dozent und Tutor bei Cubo Educativo, mit Fokus auf Programmierung und technische Kommunikation.',
          'Geschaeftsfuehrender Sekretaer der UAI-Studierendenvertretung mit Schwerpunkt auf Bindung und Wohlbefinden.',
        ],
      },
    ],
    experience: [
      {
        company: 'Grupo Axo',
        role: 'Data Scientist & Automation Analyst',
        period: 'Januar 2025 - Heute',
        highlights: [
          'Leite die Architektur autonomer Datenpipelines fuer internationalen Retail und ersetze manuelle Analyse durch automatisierte Entscheidungsablaeufe.',
          'Entwickle asynchrone RESTful APIs in Python zur Integration praediktiver Modelle in Legacy-Systeme.',
          'Entwerfe komplexe ETL/ELT-Orchestrierungen fuer Massendaten und Echtzeit-Analysen.',
        ],
      },
      {
        company: 'Al Diente App',
        role: 'Co-Founder & Full-Stack Developer',
        period: '2025',
        highlights: [
          'Co-entwickelte die komplette Al Diente Plattform und verantwortete Systemarchitektur, Backend-Services und Frontend-Implementierung.',
          'Implementierte Performance- und Skalierbarkeitsverbesserungen fuer nachhaltiges Nutzer- und Operations-Wachstum.',
        ],
      },
      {
        company: 'agon.cl',
        role: 'Co-Founder & Full-Stack Developer',
        period: '2026',
        highlights: [
          'Co-gruendete und entwickelte agon.cl als end-to-end Webplattform mit Architektur, Backend, Datenbank, REST APIs und responsive Frontend.',
          'Leitete Product Direction und UX-Umsetzung mit minimalistischem Ansatz und klarem Conversion-Fokus.',
        ],
      },
      {
        company: 'Project Orthogonal',
        role: 'AI Agent Engineer',
        period: 'Dezember 2025 - Heute',
        highlights: [
          'Entwickelte ein persistentes Multi-Agent-System mit LangGraph und PostgreSQL fuer forensische 3-way-match Rechnungspruefungen.',
          'Implementierte striktes Structured Output mit Pydantic fuer LLMs und reduzierte OCR-Halluzinationen in Produktion auf unter 1%.',
          'Entwickelte Headhunter CLI, einen autonomen Sales-Agenten fuer dynamische Prospektion und kontextuelle Textgenerierung.',
          'Rollte containerisierte Inferenz-Infrastruktur mit Docker aus, vorbereitet fuer Kubernetes-Orchestrierung.',
        ],
      },
      {
        company: 'Walmart',
        role: 'Data Analytics Intern',
        period: 'Juni 2024 - Dezember 2024',
        location: 'Santiago, Chile',
        highlights: [
          'Automatisierte Business-Intelligence-Prozesse mit fortgeschrittenem SQL und reduzierte Reporting-Zeiten um 40%.',
          'Entwickelte agentische Automatisierungsskripte mit LangChain fuer kritische HR-Prozesse.',
        ],
      },
    ],
    certifications: [
      {
        provider: 'LangChain Academy',
        name: 'Introduction to Agent Observability and Evaluations',
        period: '2025 - 2026',
      },
      {
        provider: 'LangChain Academy',
        name: 'Certified in Agentic Architectures with LangGraph',
        period: '2025 - 2026',
      },
      {
        provider: 'DeepLearning.AI',
        name: 'Advanced RAG Systems and Evaluation Driven Development',
        period: '2025 - 2026',
      },
      {
        provider: 'Cloud Native Computing',
        name: 'Deploying Scalable AI Services with Kubernetes',
        period: '2025 - 2026',
      },
    ],
  },
};
