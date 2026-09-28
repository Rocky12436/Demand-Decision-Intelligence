import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../../services/api';

const summaryCache = new Map();

export function useForecastSummary() {
  const [skus, setSkus] = useState([]);
  const [skusLoading, setSkusLoading] = useState(false);
  const [selectedSku, setSelectedSku] = useState('');
  const [selectedHorizon, setSelectedHorizon] = useState(7);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState('');
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const pollIntervalRef = useRef(null);

  // 1. Fetch available SKUs for the dropdown
  useEffect(() => {
    let isMounted = true;
    const loadSkus = async () => {
      setSkusLoading(true);
      try {
        const res = await api.get('/api/forecast/skus?limit=250');
        if (isMounted && res?.data?.products?.length > 0) {
          setSkus(res.data.products);
          if (!selectedSku) {
            setSelectedSku(res.data.products[0].product_id);
          }
        } else if (isMounted) {
          // Fallback to demand summary if /skus empty
          const fallback = await api.get('/api/demand/summary').catch(() => null);
          const topList = fallback?.data?.top_products_by_qty || [];
          const mapped = topList.map((p) => ({
            product_id: String(p.product_id),
            name: `SKU #${p.product_id}`,
            category: 'Grocery',
            total_sales: p.total_qty,
          }));
          setSkus(mapped);
          if (mapped.length > 0 && !selectedSku) {
            setSelectedSku(mapped[0].product_id);
          }
        }
      } catch (err) {
        console.error('Failed to load SKUs for forecast studio', err);
      } finally {
        if (isMounted) setSkusLoading(false);
      }
    };
    loadSkus();
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Fetch forecast summary for selected SKU and Horizon
  const fetchSummary = useCallback(
    async (sku, horizon, force = false) => {
      if (!sku) return;
      const cacheKey = `${sku}_${horizon}`;
      if (!force && summaryCache.has(cacheKey)) {
        setData(summaryCache.get(cacheKey));
        setLastUpdated(new Date().toLocaleTimeString());
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const res = await api.get(`/api/forecast/summary?sku=${encodeURIComponent(sku)}&horizon=${horizon}${force ? '&force_refresh=true' : ''}`);
        if (res?.data) {
          summaryCache.set(cacheKey, res.data);
          setData(res.data);
          setLastUpdated(new Date().toLocaleTimeString());
        }
      } catch (err) {
        console.error('Failed to load forecast summary', err);
        const msg = err.response?.data?.detail || err.response?.data?.message || err.message || 'Failed to load forecast';
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (selectedSku) {
      fetchSummary(selectedSku, selectedHorizon, false);
    }
  }, [selectedSku, selectedHorizon, fetchSummary]);

  // 3. Trigger asynchronous background forecast recomputation
  const refreshForecast = useCallback(async () => {
    if (!selectedSku || refreshing) return;
    setRefreshing(true);
    setRefreshProgress('Submitting forecast run...');
    setError(null);

    try {
      const runRes = await api.post('/api/forecast/run', {
        sku: selectedSku,
        horizon: selectedHorizon,
        force_refresh: true,
      });

      const jobId = runRes?.data?.job_id;
      if (!jobId) {
        // Fallback: synchronous refresh
        await fetchSummary(selectedSku, selectedHorizon, true);
        setRefreshing(false);
        setRefreshProgress('');
        return;
      }

      setRefreshProgress('Calculating models & intervals...');
      let attempts = 0;
      const maxAttempts = 30;

      pollIntervalRef.current = setInterval(async () => {
        attempts += 1;
        try {
          const pollRes = await api.get(`/api/forecast/jobs/${jobId}`);
          const job = pollRes?.data;

          if (job?.status === 'done' || job?.status === 'completed') {
            clearInterval(pollIntervalRef.current);
            setRefreshProgress('Finalizing results...');
            await fetchSummary(selectedSku, selectedHorizon, true);
            setRefreshing(false);
            setRefreshProgress('');
          } else if (job?.status === 'failed') {
            clearInterval(pollIntervalRef.current);
            setError(job?.error_message || 'Background forecasting run failed');
            setRefreshing(false);
            setRefreshProgress('');
          } else if (attempts >= maxAttempts) {
            clearInterval(pollIntervalRef.current);
            // Attempt summary fetch anyway
            await fetchSummary(selectedSku, selectedHorizon, true);
            setRefreshing(false);
            setRefreshProgress('');
          }
        } catch {
          // Continue polling on transient network hiccup
        }
      }, 1000);
    } catch (err) {
      console.error('Failed to initiate forecast run', err);
      // Fallback to direct summary refresh
      await fetchSummary(selectedSku, selectedHorizon, true);
      setRefreshing(false);
      setRefreshProgress('');
    }
  }, [selectedSku, selectedHorizon, refreshing, fetchSummary]);

  // Cleanup polling timer on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  return {
    data,
    loading,
    refreshing,
    refreshProgress,
    error,
    retry: () => fetchSummary(selectedSku, selectedHorizon, true),
    skus,
    skusLoading,
    selectedSku,
    setSelectedSku,
    selectedHorizon,
    setSelectedHorizon,
    refreshForecast,
    lastUpdated,
  };
}
