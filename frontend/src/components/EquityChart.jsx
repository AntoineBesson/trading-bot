import React, { useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

const EquityChart = ({ data }) => {
  const chartContainerRef = useRef();

  useEffect(() => {
    if (!data || data.length === 0) return;

    // 1. Create Chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#1f2937' }, // Dark Gray (Tailwind bg-gray-800)
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#374151' },
        horzLines: { color: '#374151' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 300,
    });

    // 2. Add Line Series (Equity)
    const newSeries = chart.addAreaSeries({
      lineColor: '#22c55e', // Green
      topColor: '#22c55e',
      bottomColor: 'rgba(34, 197, 94, 0.1)', // Transparent Green
    });

    // 3. Format Data (TradingView expects { time, value })
    // We convert UNIX timestamp to seconds if needed
    const formattedData = data
      .filter(d => d && typeof d.time === 'number' && typeof d.value === 'number')
      .map(d => ({
        time: Math.floor(d.time), // Unix Timestamp
        value: d.value
    }));
    
    // Sort by time just in case
    formattedData.sort((a, b) => a.time - b.time);

    if (formattedData.length > 0) {
        newSeries.setData(formattedData);
        chart.timeScale().fitContent();
    }

    // Resize handler
    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current.clientWidth });
    };
    window.addEventListener('resize', handleResize);

    return () => {
      chart.remove();
      window.removeEventListener('resize', handleResize);
    };
  }, [data]);

  return (
    <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 shadow-lg w-full max-w-5xl mt-6">
      <h2 className="text-xl font-bold mb-4 text-gray-200">Portfolio Performance</h2>
      <div ref={chartContainerRef} className="w-full h-[300px]" />
    </div>
  );
};

export default EquityChart;