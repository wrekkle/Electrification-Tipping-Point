(function (root) {
  function computeLayout(opts) {
    var count = opts.count;
    var width = opts.width;
    var maxHeight = opts.maxHeight;
    var minSize = opts.minSize !== undefined ? opts.minSize : 10;
    var maxSize = opts.maxSize !== undefined ? opts.maxSize : 32;
    var gapRatio = opts.gapRatio !== undefined ? opts.gapRatio : 0.35;

    if (!(count > 0)) {
      return { cols: 0, rows: 0, size: 0, gap: 0, gridWidth: 0, gridHeight: 0, overflow: false };
    }

    if (!(width > 0)) {
      var c0 = Math.ceil(Math.sqrt(Math.max(count, 1)));
      var r0 = Math.ceil(count / c0);
      return {
        cols: c0,
        rows: r0,
        size: minSize,
        gap: minSize * gapRatio,
        gridWidth: c0 * minSize + (c0 - 1) * minSize * gapRatio,
        gridHeight: r0 * minSize + (r0 - 1) * minSize * gapRatio,
        overflow: true
      };
    }

    var limit = Math.min(count, 400);
    var candidates = [];
    for (var cols = 1; cols <= limit; cols++) {
      var rows = Math.ceil(count / cols);
      var sizeW = width / (cols + (cols - 1) * gapRatio);
      var sizeH = (Number.isFinite(maxHeight) && maxHeight > 0)
        ? maxHeight / (rows + (rows - 1) * gapRatio)
        : maxSize;
      var size = Math.min(sizeW, sizeH, maxSize);
      var overflow = size < minSize;
      if (overflow) size = minSize;
      candidates.push({ cols: cols, rows: rows, size: size, overflow: overflow });
    }

    var pool = candidates.filter(function (cand) { return !cand.overflow; });
    var anyOverflow = pool.length === 0;
    if (anyOverflow) pool = candidates;

    var targetRatio = Number.isFinite(opts.targetAspect) && opts.targetAspect > 0
      ? opts.targetAspect
      : ((Number.isFinite(maxHeight) && maxHeight > 0) ? width / maxHeight : width / (width * 0.6));

    pool.sort(function (a, b) {
      if (b.size !== a.size) return b.size - a.size;
      if (Math.abs(a.size - b.size) <= 1e-6) {
        var ra = Math.abs(a.cols / a.rows - targetRatio);
        var rb = Math.abs(b.cols / b.rows - targetRatio);
        if (ra !== rb) return ra - rb;
      }
      var wa = a.cols * a.rows - count;
      var wb = b.cols * b.rows - count;
      if (wa !== wb) return wa - wb;
      return a.cols - b.cols;
    });

    var best = pool[0];
    var gap = best.size * gapRatio;
    var gridWidth = best.cols * best.size + (best.cols - 1) * gap;
    var gridHeight = best.rows * best.size + (best.rows - 1) * gap;

    return {
      cols: best.cols,
      rows: best.rows,
      size: best.size,
      gap: gap,
      gridWidth: gridWidth,
      gridHeight: gridHeight,
      overflow: anyOverflow || best.size < minSize
    };
  }

  root.DotGrid = { computeLayout: computeLayout };
})(typeof globalThis !== 'undefined' ? globalThis : this);
