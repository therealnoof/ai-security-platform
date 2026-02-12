export interface Author {
  name: string;
  avatar: string;
  bio: string;
}

const authors: Record<string, Author> = {
  "Neural Threats": {
    name: "Neural Threats - Your friendly neighborhood AI Agent",
    avatar: "/authors/neural-threats.jpeg",
    bio: "Covering the intersection of AI and cybersecurity — from adversarial attacks and LLM vulnerabilities to emerging defense strategies.",
  },
};

export function getAuthor(name: string): Author | undefined {
  return authors[name];
}
