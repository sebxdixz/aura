export interface Project {
  id: string;
  name: string;
  description: string;
  videoUrl?: string;
  imageUrl?: string;
  techs: string[];
  links: {
    website?: string;
    github?: string;
    demo?: string;
  };
}

export const PROJECTS: Project[] = [
  {
    id: 'agon',
    name: 'Agon.cl',
    description: 'Plataforma web completa con sistema backend robusto y diseno UI/UX minimalista. Desarrollo end-to-end: arquitectura, base de datos, APIs REST, frontend responsive y estetica visual.',
    techs: ['React', 'TypeScript', 'Node.js', 'PostgreSQL', 'CSS3', 'REST API'],
    links: {
      website: 'https://agon.cl',
      demo: 'https://agon.cl'
    }
  },
  {
    id: 'aldiente',
    name: 'Al Diente App',
    description: 'Co-creador de plataforma integral. Responsable de sistemas, backend architecture, frontend components y optimizacion de performance. Trabajo colaborativo en arquitectura y escalabilidad.',
    techs: ['React', 'TypeScript', 'Node.js', 'MongoDB', 'Express', 'WebSocket'],
    links: {
      website: 'https://www.aldiente.app',
      demo: 'https://www.aldiente.app'
    }
  },
  {
    id: 'jober',
    name: 'JOBER',
    description: 'Agente IA autonomo para automatizacion inteligente de procesos. Sistema multi-agente con capacidades de reasoning, planning y ejecucion automatica de tareas.',
    techs: ['Claude API', 'AI Agents', 'Python', 'TypeScript', 'Automation', 'LLM'],
    links: {
      github: 'https://github.com/sebxdixz/jober'
    }
  },
  {
    id: 'orthogonal',
    name: 'Orthogonal',
    description: 'Framework de agentes IA para analisis y procesamiento de datos complejos. Sistema de reasoning avanzado con capacidades de multi-turn conversations y task decomposition.',
    techs: ['Claude API', 'AI Agents', 'Python', 'Data Processing', 'LLM', 'Reasoning'],
    links: {
      github: 'https://github.com/sebxdixz/orthogonal'
    }
  },
  {
    id: 'nation',
    name: 'Nation',
    description: 'Proyecto orientado a ingenieria de agentes IA, con foco en diseno de flujos autonomos, herramientas y automatizaciones para operaciones reales.',
    techs: ['AI Agents', 'Python', 'Automation', 'Prompt Engineering', 'LLM', 'Orchestration'],
    links: {
      github: 'https://github.com/sebxdixz/nation'
    }
  }
];
