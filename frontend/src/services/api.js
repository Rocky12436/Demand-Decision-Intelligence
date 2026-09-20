import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

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

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.detail || "Sales upload failed"
    );
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