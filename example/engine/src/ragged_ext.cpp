// This code is a Qiskit project.
//
// (C) Copyright IBM 2026.
//
// This code is licensed under the Apache License, Version 2.0. You may
// obtain a copy of this license in the LICENSE.txt file in the root directory
// of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
//
// Any modifications or derivative works of this code must retain this
// copyright notice, and modified files need to carry a notice indicating
// that they have been altered from the originals.

// The "fused" acceleration engine for the coheriq_ragged_domain example,
// implemented in C++ and exposed to Python with nanobind.
//
// This is the compiled counterpart of what used to be a pure-Python engine.
// It provides the same public API as the domain's RaggedBatch container and the
// free functions that operate on it, so coheriq can swap it in transparently.
//
// The storage is contiguous (CSR-style): a single flat `values_` buffer plus an
// `offsets_` array, where row i is values_[offsets_[i] : offsets_[i + 1]].

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <tuple>
#include <vector>

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

namespace nb = nanobind;
using namespace nb::literals;

namespace {

// A batch of variable-length numeric rows, stored contiguously.
struct RaggedBatch {
  std::vector<double> values_;
  std::vector<std::int64_t> offsets_;

  // Build from an iterable of rows (an iterable of floats each).  Mirrors the
  // pure-Python __init__: flatten once into contiguous storage.
  explicit RaggedBatch(nb::iterable rows) {
    offsets_.push_back(0);
    for (nb::handle row : rows) {
      for (nb::handle x : row) {
        values_.push_back(nb::cast<double>(x));
      }
      offsets_.push_back(static_cast<std::int64_t>(values_.size()));
    }
  }

  // Direct construction from already-flat storage.  The C++ analogue of the
  // Python engine's __new__-based fast path.
  RaggedBatch(std::vector<double> values, std::vector<std::int64_t> offsets)
      : values_(std::move(values)), offsets_(std::move(offsets)) {}

  std::size_t len() const { return offsets_.size() - 1; }

  // Return row i as a fresh list (a copy, never a view).  nanobind converts the
  // returned std::vector into an owned Python list, so callers get value
  // semantics and nothing borrows into our storage.
  std::vector<double> getitem(std::int64_t i) const {
    if (i < 0 || static_cast<std::size_t>(i) >= len()) {
      throw nb::index_error("RaggedBatch row index out of range");
    }
    std::int64_t start = offsets_[static_cast<std::size_t>(i)];
    std::int64_t stop = offsets_[static_cast<std::size_t>(i) + 1];
    return std::vector<double>(values_.begin() + start, values_.begin() + stop);
  }

  std::vector<std::int64_t> row_lengths() const {
    std::vector<std::int64_t> lengths;
    lengths.reserve(len());
    for (std::size_t i = 0; i < len(); ++i) {
      lengths.push_back(offsets_[i + 1] - offsets_[i]);
    }
    return lengths;
  }

  std::string repr() const {
    return "RaggedBatch(" + std::to_string(len()) + " rows, fused backend)";
  }
};

// Build a RaggedBatch from a flat values buffer and offsets.  Validates the
// offsets so a malformed call raises rather than corrupting storage (or, worse,
// reading out of bounds later).
RaggedBatch ragged_batch_from_flat(std::vector<double> values,
                                   std::vector<std::int64_t> offsets) {
  if (offsets.empty() || offsets.front() != 0) {
    throw nb::value_error("offsets must be non-empty and start at 0");
  }
  for (std::size_t i = 1; i < offsets.size(); ++i) {
    if (offsets[i] < offsets[i - 1]) {
      throw nb::value_error("offsets must be non-decreasing");
    }
  }
  if (offsets.back() != static_cast<std::int64_t>(values.size())) {
    throw nb::value_error("offsets.back() must equal len(values)");
  }
  return RaggedBatch(std::move(values), std::move(offsets));
}

// Per-row softmax computed straight over the contiguous flat buffer: find the
// row max, exponentiate while accumulating the sum, then normalize in place.
RaggedBatch segmented_softmax(const RaggedBatch &batch) {
  const std::vector<double> &src = batch.values_;
  const std::vector<std::int64_t> &offsets = batch.offsets_;
  std::vector<double> out(src.size(), 0.0);
  for (std::size_t i = 0; i < batch.len(); ++i) {
    std::int64_t start = offsets[i];
    std::int64_t stop = offsets[i + 1];
    if (start == stop) {
      continue;
    }
    double m = src[static_cast<std::size_t>(start)];
    for (std::int64_t j = start + 1; j < stop; ++j) {
      if (src[static_cast<std::size_t>(j)] > m) {
        m = src[static_cast<std::size_t>(j)];
      }
    }
    double total = 0.0;
    for (std::int64_t j = start; j < stop; ++j) {
      double e = std::exp(src[static_cast<std::size_t>(j)] - m);
      out[static_cast<std::size_t>(j)] = e;
      total += e;
    }
    for (std::int64_t j = start; j < stop; ++j) {
      out[static_cast<std::size_t>(j)] /= total;
    }
  }
  return RaggedBatch(std::move(out), offsets);
}

// Per-row top-k softmax: select the top k values (partial selection rather than
// a full sort), then compute a stable softmax over just those.  Returns, per
// row, a list of (index, probability) pairs; indices refer into the input row.
std::vector<std::vector<std::tuple<std::int64_t, double>>>
segmented_topk_softmax(const RaggedBatch &batch, std::int64_t k) {
  const std::vector<double> &src = batch.values_;
  const std::vector<std::int64_t> &offsets = batch.offsets_;
  std::vector<std::vector<std::tuple<std::int64_t, double>>> result;
  result.reserve(batch.len());

  for (std::size_t i = 0; i < batch.len(); ++i) {
    std::int64_t start = offsets[i];
    std::int64_t stop = offsets[i + 1];
    std::int64_t row_len = stop - start;
    std::vector<std::tuple<std::int64_t, double>> row_out;
    if (row_len == 0) {
      result.push_back(std::move(row_out));
      continue;
    }

    // Row-local indices paired with their values.
    std::vector<std::pair<std::int64_t, double>> ranked;
    ranked.reserve(static_cast<std::size_t>(row_len));
    for (std::int64_t j = 0; j < row_len; ++j) {
      ranked.emplace_back(j, src[static_cast<std::size_t>(start + j)]);
    }

    std::int64_t keep = std::min(k, row_len);
    if (keep < 0) {
      keep = 0;
    }
    // Partition so the top `keep` by value come first (O(n)); then sort just
    // those descending for a deterministic order.
    std::nth_element(
        ranked.begin(), ranked.begin() + keep, ranked.end(),
        [](const std::pair<std::int64_t, double> &a,
           const std::pair<std::int64_t, double> &b) { return a.second > b.second; });
    std::stable_sort(
        ranked.begin(), ranked.begin() + keep,
        [](const std::pair<std::int64_t, double> &a,
           const std::pair<std::int64_t, double> &b) { return a.second > b.second; });

    double m = ranked[0].second;
    for (std::int64_t j = 1; j < keep; ++j) {
      if (ranked[static_cast<std::size_t>(j)].second > m) {
        m = ranked[static_cast<std::size_t>(j)].second;
      }
    }
    double total = 0.0;
    std::vector<double> exps(static_cast<std::size_t>(keep));
    for (std::int64_t j = 0; j < keep; ++j) {
      double e = std::exp(ranked[static_cast<std::size_t>(j)].second - m);
      exps[static_cast<std::size_t>(j)] = e;
      total += e;
    }
    row_out.reserve(static_cast<std::size_t>(keep));
    for (std::int64_t j = 0; j < keep; ++j) {
      row_out.emplace_back(ranked[static_cast<std::size_t>(j)].first,
                           exps[static_cast<std::size_t>(j)] / total);
    }
    result.push_back(std::move(row_out));
  }
  return result;
}

}  // namespace

NB_MODULE(_ragged_ext, m) {
  nb::class_<RaggedBatch>(m, "RaggedBatch")
      .def(nb::init<nb::iterable>(), "rows"_a)
      .def_prop_ro("backend", [](const RaggedBatch &) { return "fused"; })
      .def("__len__", &RaggedBatch::len)
      .def("__getitem__", &RaggedBatch::getitem, "i"_a)
      .def("__iter__",
           [](const RaggedBatch &self) {
             // Yield each row as a copied list, matching __getitem__ semantics.
             // Build a Python list of the rows and return its iterator; the list
             // owns the copies, so there is no borrowing into our storage.
             nb::list rows;
             for (std::size_t i = 0; i < self.len(); ++i) {
               rows.append(nb::cast(self.getitem(static_cast<std::int64_t>(i))));
             }
             return nb::iter(rows);
           })
      .def("row_lengths", &RaggedBatch::row_lengths)
      .def("__repr__", &RaggedBatch::repr)
      .def_ro("_values", &RaggedBatch::values_)
      .def_ro("_offsets", &RaggedBatch::offsets_);

  m.def("ragged_batch_from_flat", &ragged_batch_from_flat, "values"_a, "offsets"_a);
  m.def("segmented_softmax", &segmented_softmax, "batch"_a);
  m.def("segmented_topk_softmax", &segmented_topk_softmax, "batch"_a, "k"_a);
}
