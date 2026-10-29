export const TEST_PROJECT = {
  clientName: process.env.E2E_CLIENT_NAME || 'Northwind Builders',
  websiteUrl: process.env.E2E_SITE_URL || 'https://www.northwind-builders.example.com/',
  keywords: ['Home Remodeling', 'Home Builder', 'Kitchen Remodeling', 'Bathroom Remodeling'],
  font: 'Montserrat',
  imagesPerPage: 3,
} as const;

export const API_ENDPOINTS = {
  health: '/health',
  projects: '/api/projects',
  projectStatus: (id: string) => `/api/projects/${id}/status`,
  projectDetail: (id: string) => `/api/projects/${id}`,
  projectConfirm: (id: string) => `/api/projects/${id}/confirm`,
  generationStatus: (id: string) => `/api/projects/${id}/generation-status`,
  projectDownload: (id: string) => `/api/projects/${id}/download`,
} as const;
