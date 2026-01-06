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
        background: { type: ColorType.Solid, color: '#141414' },
        textColor: '#a3a3a3',
      },
      grid: {
        vertLines: { color: '#262626' },
        horzLines: { color: '#262626' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 350,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#262626',
      },
      rightPriceScale: {
        borderColor: '#262626',
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: '#404040',
          width: 1,
          style: 2,
          labelBackgroundColor: '#1f1f1f',
        },
        horzLine: {
          color: '#404040',
          width: 1,
          style: 2,
          labelBackgroundColor: '#1f1f1f',
        },
      },
    });

    // Create Series
    let newSeries;
    try {
        if (typeof chart.addAreaSeries === 'function') {
            newSeries = chart.addAreaSeries({
                lineColor: '#22c55e',
                topColor: 'rgba(34, 197, 94, 0.3)',
                bottomColor: 'rgba(34, 197, 94, 0.02)',
                lineWidth: 2,
            });
        } else {
            newSeries = chart.addLineSeries({ 
              color: '#22c55e',
              lineWidth: 2,
            });
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
    <div ref={chartContainerRef} className="w-full rounded-lg overflow-hidden" style={{ height: '350px' }} />
  );
};

export default EquityChart;