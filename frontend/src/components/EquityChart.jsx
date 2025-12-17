import React, { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

const EquityChart = ({ data }) => {
  const chartContainerRef = useRef();
  const chartRef = useRef(null);
  const seriesRef = useRef(null);

  // 1. Initialize Chart (Run once)
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1f2937' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Create Series
    let newSeries;
    try {
        if (typeof chart.addAreaSeries === 'function') {
            newSeries = chart.addAreaSeries({
                lineColor: '#22c55e',
                topColor: '#22c55e',
                bottomColor: 'rgba(34, 197, 94, 0.1)',
            });
        } else {
            newSeries = chart.addLineSeries({ color: '#22c55e' });
        }
    } catch (err) {
        console.error("Error creating series:", err);
    }

    chartRef.current = chart;
    seriesRef.current = newSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []); // Empty dependency array = run once

  // 2. Update Data (Run when data changes)
  useEffect(() => {
    if (!data || data.length === 0 || !seriesRef.current) return;

    const formattedData = data
      .filter(d => d && typeof d.time === 'number' && typeof d.value === 'number')
      .map(d => ({
        time: Math.floor(d.time),
        value: d.value
    }));
    
    // Sort and deduplicate
    formattedData.sort((a, b) => a.time - b.time);
    const uniqueData = [];
    if (formattedData.length > 0) {
        uniqueData.push(formattedData[0]);
        for (let i = 1; i < formattedData.length; i++) {
            if (formattedData[i].time > formattedData[i-1].time) {
                uniqueData.push(formattedData[i]);
            }
        }
    }

    if (uniqueData.length > 0) {
        seriesRef.current.setData(uniqueData);
        chartRef.current.timeScale().fitContent();
    }
  }, [data]);

  return (
    <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 shadow-lg w-full max-w-5xl mt-6">
      <h2 className="text-xl font-bold mb-4 text-gray-200">Portfolio Performance</h2>
      <div ref={chartContainerRef} className="w-full" style={{ height: '300px' }} />
    </div>
  );
};

export default EquityChart;