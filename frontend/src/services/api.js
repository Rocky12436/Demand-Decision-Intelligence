import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

// Attach JWT token from localStorage and normalize /api paths
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ddi_access_token") || localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (config.url && config.url.startsWith('/api')) {
    config.url = config.url.replace(/^\/api/, '');
  }
  return config;
});

export { API_BASE_URL };
export async function uploadSalesFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${API_BASE_URL}/upload/sales`,
    {
      method: "POST",
      body: formData,
    }
  );

  let data;
  try {
    data = await response.json();
  } catch (e) {
    throw new Error("Invalid response format from server");
  }

  if (!response.ok) {
    // If backend returns a structured validation response (e.g. 422 with REJECTED status, unmapped_skus, or error_breakdown)
    if (data && (data.status || data.error_breakdown || data.unmapped_skus)) {
      return data;
    }
    throw new Error(data.detail || "Sales upload failed");
  }

  return data;
}

export async function resolveSkus(uploadId, mappings) {
  const response = await fetch(`${API_BASE_URL}/upload/${uploadId}/resolve-skus`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ mappings }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Failed to resolve SKUs");
  }
  return data;
}

export async function getProducts(limit = 100) {
  const response = await fetch(`${API_BASE_URL}/products?limit=${limit}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Failed to fetch products");
  return data.products || [];
}

export function getFailedRowsDownloadUrl(uploadId) {
  return `${API_BASE_URL}/upload/${uploadId}/failed-rows`;
}

export async function recomputeForecast(datasetId = null, productIds = null) {
  const response = await fetch(`${API_BASE_URL}/forecast/recompute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      dataset_id: datasetId,
      product_ids: productIds,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Failed to recompute forecast");
  }
  return data;
}


export async function getUploads() {
  const response = await fetch(
    `${API_BASE_URL}/upload/uploads`
  );

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.detail || "Failed to fetch uploads"
    );
  }

  return data;
}


export async function getUpload(uploadId) {
  const response = await fetch(
    `${API_BASE_URL}/upload/uploads/${uploadId}`
  );

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.detail || "Failed to fetch upload"
    );
  }

  return data;
}


export async function getValidationResults(uploadId) {
  const response = await fetch(
    `${API_BASE_URL}/upload/validation/${uploadId}`
  );

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.detail ||
        "Failed to fetch validation results"
    );
  }

  return data;
}

export async function getPricingElasticity(limit = 100, classification = "", category = "") {
  let url = `${API_BASE_URL}/pricing/elasticity?limit=${limit}`;
  if (classification) url += `&classification=${encodeURIComponent(classification)}`;
  if (category) url += `&category=${encodeURIComponent(category)}`;

  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Failed to fetch pricing elasticity");
  return data;
}

export async function getPricingRecommendations(category = "", limit = 100) {
  let url = `${API_BASE_URL}/pricing/recommendations?limit=${limit}`;
  if (category) url += `&category=${encodeURIComponent(category)}`;

  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Failed to fetch pricing recommendations");
  return data;
}

export async function recalculateElasticity() {
  const response = await fetch(`${API_BASE_URL}/pricing/recalculate`, {
    method: "POST"
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Failed to recalculate elasticity");
  return data;
}

export default api;