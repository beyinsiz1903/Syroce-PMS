import React, { useState, useEffect, useRef, memo } from 'react';
import { VariableSizeList as List } from 'react-window';

const VirtualizedGrid = ({ items, renderCard, categoryHeader, itemHeight = 220, headerHeight = 60, minCardWidth = 300, gap = 12 }) => {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  if (width === 0) {
    return <div ref={containerRef} className="w-full h-full min-h-[400px]" />;
  }

  // Calculate columns based on width and minCardWidth
  const cols = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
  
  // Flatten items into rows
  const rows = [];
  const grouped = items.reduce((acc, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {});

  Object.entries(grouped).forEach(([cat, catItems]) => {
    rows.push({ type: 'header', category: cat, count: catItems.length });
    for (let i = 0; i < catItems.length; i += cols) {
      rows.push({ type: 'row', items: catItems.slice(i, i + cols) });
    }
  });

  const getRowHeight = (index) => {
    return rows[index].type === 'header' ? headerHeight : itemHeight + gap;
  };

  const Row = memo(({ index, style }) => {
    const row = rows[index];
    if (row.type === 'header') {
      return (
        <div style={{ ...style, width: '100%' }}>
          {categoryHeader(row.category, row.count)}
        </div>
      );
    }

    const cardWidth = (width - gap * (cols - 1)) / cols;

    return (
      <div style={{ ...style, display: 'flex', gap: `${gap}px`, width: '100%', paddingBottom: `${gap}px` }}>
        {row.items.map((item, i) => (
          <div key={item.id || i} style={{ width: cardWidth }}>
            {renderCard(item)}
          </div>
        ))}
      </div>
    );
  });
  
  Row.displayName = 'VirtualizedGridRow';

  return (
    <div ref={containerRef} className="w-full h-[600px] border rounded-lg p-4 bg-white">
      <List
        height={600}
        itemCount={rows.length}
        itemSize={getRowHeight}
        width={width}
      >
        {Row}
      </List>
    </div>
  );
};

export default VirtualizedGrid;
