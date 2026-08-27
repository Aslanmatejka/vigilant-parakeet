import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PropTypes from 'prop-types'
import { toast } from 'react-toastify'
import supabase from '../../utils/supabaseClient.js'
import aiChatService from '../../utils/services/aiChatService.js'
import {
  parseListingsCsv,
  downloadCsvTemplate,
  sanitizeListingExpiry,
  matchCommunityByName,
} from '../../utils/csvListings.js'
import { assignImagestoRows } from '../../utils/foodImages.js'
import { reportError } from '../../utils/helpers.js'

const MAX_CSV_BYTES = 2 * 1024 * 1024
const MAX_ROWS = 100
const CATEGORIES = ['produce', 'bakery', 'dairy', 'pantry', 'meat', 'prepared', 'other']

/**
 * Production bulk CSV upload for Share Food.
 * Same pipeline as Nouri: parseListingsCsv → enrich (soft) → /api/ai/bulk-listings.
 * Does not touch the individual FoodForm path.
 */
function ShareBulkCsvPanel({
  userId,
  preferredCommunityId = null,
  preferredLocation = '',
  lockToUserCommunity = false,
  onSuccess,
}) {
  const fileInputRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [enriching, setEnriching] = useState(false)
  const [filename, setFilename] = useState('')
  const [rows, setRows] = useState([])
  const [parseErrors, setParseErrors] = useState([])
  const [fatalError, setFatalError] = useState('')
  const [enrichSummary, setEnrichSummary] = useState('')
  const [apiErrors, setApiErrors] = useState([])

  const [communities, setCommunities] = useState([])
  const [communitiesLoading, setCommunitiesLoading] = useState(true)
  const [communitiesError, setCommunitiesError] = useState(null)

  const [selectedRowIndexes, setSelectedRowIndexes] = useState(() => new Set())
  const [bulkLocation, setBulkLocation] = useState(() => String(preferredLocation || '').trim())
  const [bulkCommunityId, setBulkCommunityId] = useState(() =>
    preferredCommunityId != null && preferredCommunityId !== ''
      ? String(preferredCommunityId)
      : '',
  )
  const [bulkCategory, setBulkCategory] = useState('')
  const [bulkExpiry, setBulkExpiry] = useState('')
  const [fillEmptyOnly, setFillEmptyOnly] = useState(true)

  const loadCommunities = useCallback(async () => {
    setCommunitiesLoading(true)
    setCommunitiesError(null)
    try {
      const { data, error } = await supabase
        .from('communities')
        .select('id, name')
        .eq('is_active', true)
        .order('name', { ascending: true })
      if (error) throw error
      setCommunities(data || [])
    } catch (err) {
      setCommunities([])
      setCommunitiesError(err?.message || 'Could not load communities')
    } finally {
      setCommunitiesLoading(false)
    }
  }, [])

  useEffect(() => {
    loadCommunities()
  }, [loadCommunities])

  // Resolve community names → ids; prefill preferred only when row has neither.
  // Non-admin donors are locked to their signup community (same as FoodForm).
  useEffect(() => {
    if (!communities.length || !rows.length) return
    const preferred = preferredCommunityId
      ? communities.find((c) => String(c.id) === String(preferredCommunityId))
      : null
    let changed = false
    const next = rows.map((row) => {
      if (lockToUserCommunity && preferred) {
        if (
          String(row.community_id) !== String(preferred.id)
          || row.community_name !== preferred.name
        ) {
          changed = true
          return {
            ...row,
            community_id: String(preferred.id),
            community_name: preferred.name,
          }
        }
        return row
      }
      if (row?.community_id) {
        if (!row.community_name) {
          const byId = communities.find((c) => String(c.id) === String(row.community_id))
          if (byId) {
            changed = true
            return { ...row, community_name: byId.name }
          }
        }
        return row
      }
      if (row?.community_name) {
        const match = matchCommunityByName(row.community_name, communities)
        if (match) {
          changed = true
          return {
            ...row,
            community_id: String(match.id),
            community_name: match.name,
          }
        }
        return row
      }
      if (preferred) {
        changed = true
        return {
          ...row,
          community_id: String(preferred.id),
          community_name: preferred.name,
        }
      }
      return row
    })
    if (changed) setRows(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-resolve when communities / row count / lock change
  }, [communities, preferredCommunityId, rows.length, lockToUserCommunity])

  useEffect(() => {
    const n = rows.length
    setSelectedRowIndexes(new Set(Array.from({ length: n }, (_, i) => i)))
    setBulkLocation((prev) => {
      if (String(prev || '').trim()) return prev
      return String(preferredLocation || '').trim()
    })
    setBulkCommunityId((prev) => {
      if (String(prev || '').trim()) return prev
      return preferredCommunityId != null && preferredCommunityId !== ''
        ? String(preferredCommunityId)
        : ''
    })
  }, [rows.length, preferredLocation, preferredCommunityId])

  const selectableCommunities = useMemo(() => {
    if (!lockToUserCommunity || preferredCommunityId == null || preferredCommunityId === '') {
      return communities
    }
    return communities.filter((c) => String(c.id) === String(preferredCommunityId))
  }, [communities, lockToUserCommunity, preferredCommunityId])


  const missingCommunity = useMemo(
    () => rows.some((r) => !r?.community_id && !String(r?.community_name || '').trim()),
    [rows],
  )

  const allSelected = rows.length > 0 && selectedRowIndexes.size === rows.length
  const someSelected = selectedRowIndexes.size > 0 && selectedRowIndexes.size < rows.length

  const selectAllRef = (el) => {
    if (el) el.indeterminate = someSelected
  }

  const updateRow = useCallback((idx, patch) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  }, [])

  const updateRows = useCallback((indices, patch) => {
    const indexSet = new Set(Array.isArray(indices) ? indices : [])
    if (!indexSet.size || !patch) return
    setRows((prev) => prev.map((r, i) => (indexSet.has(i) ? { ...r, ...patch } : r)))
  }, [])

  const removeRow = useCallback((idx) => {
    setRows((prev) => prev.filter((_, i) => i !== idx))
    setSelectedRowIndexes((prev) => {
      const next = new Set()
      prev.forEach((i) => {
        if (i < idx) next.add(i)
        else if (i > idx) next.add(i - 1)
      })
      return next
    })
  }, [])

  const applyPatchToSelected = (patch, isEmptyRow) => {
    if (!patch || !selectedRowIndexes.size) return
    const indexes = Array.from(selectedRowIndexes).filter((idx) => {
      if (!fillEmptyOnly) return true
      if (typeof isEmptyRow !== 'function') return true
      return isEmptyRow(rows[idx])
    })
    if (!indexes.length) return
    updateRows(indexes, patch)
  }

  const applyCommunityToSelected = () => {
    const id = String(bulkCommunityId || '').trim()
    if (!id) return
    const match = selectableCommunities.find((c) => String(c.id) === id)
    if (!match) return
    applyPatchToSelected(
      { community_id: String(match.id), community_name: match.name },
      (r) => !r?.community_id && !String(r?.community_name || '').trim(),
    )
  }

  const applyLocationToSelected = () => {
    const location = String(bulkLocation || '').trim()
    if (!location) return
    applyPatchToSelected({ location }, (r) => !String(r?.location || '').trim())
  }

  const applyCategoryToSelected = () => {
    const category = String(bulkCategory || '').trim()
    if (!category) return
    applyPatchToSelected(
      { category },
      (r) => !String(r?.category || '').trim() || String(r?.category).toLowerCase() === 'other',
    )
  }

  const applyExpiryToSelected = () => {
    const expiry = String(bulkExpiry || '').trim()
    if (!expiry) return
    applyPatchToSelected({ expiry_date: expiry }, (r) => !String(r?.expiry_date || '').trim())
  }

  const applyAllMissingToSelected = () => {
    if (String(bulkCommunityId || '').trim()) applyCommunityToSelected()
    if (String(bulkLocation || '').trim()) applyLocationToSelected()
    if (String(bulkCategory || '').trim()) applyCategoryToSelected()
    if (String(bulkExpiry || '').trim()) applyExpiryToSelected()
  }

  const reset = () => {
    setRows([])
    setFilename('')
    setParseErrors([])
    setFatalError('')
    setEnrichSummary('')
    setApiErrors([])
    setSelectedRowIndexes(new Set())
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleFileSelected = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return

    reset()
    setFilename(file.name)

    if (file.size > MAX_CSV_BYTES) {
      setFatalError('CSV too large (max 2 MB).')
      return
    }

    setBusy(true)
    try {
      const text = await file.text()
      const { rows: parsed, errors } = parseListingsCsv(text)
      const capped = (parsed || []).slice(0, MAX_ROWS)
      const withImages = assignImagestoRows(capped)
      setParseErrors(Array.isArray(errors) ? errors : [])

      if (!withImages.length) {
        setFatalError(
          (errors && errors[0]) || 'CSV had no valid rows. Check the template columns.',
        )
        return
      }

      setRows(withImages)

      if (userId) {
        setEnriching(true)
        try {
          const enrichment = await aiChatService.enrichListings(withImages, {
            userId,
            language: 'en',
          })
          if (enrichment?.rows?.length) {
            setRows(assignImagestoRows(enrichment.rows))
            setEnrichSummary(
              enrichment.summary
              || ((enrichment.filled || []).length
                ? `AI filled gaps on ${(enrichment.filled || []).length} row(s). Review before publishing.`
                : 'AI reviewed your rows — no gaps to fill.'),
            )
          }
        } catch {
          // Soft-fail: user can still publish as-is.
        } finally {
          setEnriching(false)
        }
      }
    } catch (err) {
      reportError(err)
      setFatalError(err?.message || 'Could not read CSV file.')
    } finally {
      setBusy(false)
    }
  }

  const handleConfirm = async () => {
    if (!rows.length || busy) return
    if (!userId) {
      toast.error('Sign in to publish listings.', { position: 'top-center' })
      return
    }
    if (missingCommunity) {
      toast.error('Choose a school or community for each listing.', { position: 'top-center' })
      return
    }

    setBusy(true)
    setApiErrors([])
    try {
      const rowsToCreate = rows.map((r) => {
        const cleaned = sanitizeListingExpiry(r)
        return {
          ...cleaned,
          community_id: cleaned.community_id != null ? String(cleaned.community_id) : undefined,
          community_name: cleaned.community_name || undefined,
        }
      })

      const result = await aiChatService.bulkCreateListings(rowsToCreate, { userId })
      const { created, failed, awaitingApproval, errors } = result

      if (Array.isArray(errors) && errors.length) {
        setApiErrors(errors.slice(0, 8))
      }

      if (!created) {
        toast.error(
          failed
            ? `Could not create listings (${failed} failed). Check community and required fields.`
            : 'Bulk create failed.',
          { position: 'top-center' },
        )
        return
      }

      window.dispatchEvent(new CustomEvent('foodShared'))

      toast.success(
        awaitingApproval
          ? `${created} listing${created === 1 ? '' : 's'} submitted for admin approval${failed ? ` — ${failed} failed` : ''}`
          : `${created} listing${created === 1 ? '' : 's'} created successfully${failed ? ` — ${failed} failed` : ''}`,
        { autoClose: 5000, position: 'top-center' },
      )

      if (typeof onSuccess === 'function') {
        onSuccess({ created, failed, awaitingApproval })
      } else {
        reset()
      }
    } catch (err) {
      reportError(err)
      toast.error(err?.message || 'Bulk create failed.', { position: 'top-center' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5" data-name="share-bulk-csv-panel">
      <div className="rounded-xl border border-[#2CABE3]/20 bg-gradient-to-br from-[#2CABE3]/5 to-emerald-50/50 p-4 sm:p-5">
        <h2 className="text-lg font-semibold text-gray-900">Bulk CSV upload</h2>
        <p className="mt-1 text-sm text-gray-600">
          Upload up to {MAX_ROWS} listings at once. Same rules as a single share — each row needs a
          school/community, and listings may wait for admin approval before Find Food.
        </p>
        <ul className="mt-3 text-xs text-gray-500 space-y-1 list-disc list-inside">
          <li>Required columns: title, quantity, unit, category</li>
          <li>Optional: description, expiry_date (MM/DD/YYYY), location, community, dietary_tags, allergens</li>
          <li>Images are assigned automatically when missing (you can still edit rows below)</li>
        </ul>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={downloadCsvTemplate}
            disabled={busy}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border border-[#2CABE3]/30 bg-white text-[#1a7a9e] hover:bg-[#2CABE3]/10 disabled:opacity-50"
          >
            <i className="fas fa-download text-xs" aria-hidden="true" />
            Download template
          </button>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold bg-[#2CABE3] text-white hover:bg-[#2299c7] disabled:opacity-50 shadow-sm"
          >
            <i className="fas fa-file-csv text-xs" aria-hidden="true" />
            {rows.length ? 'Replace CSV' : 'Choose CSV'}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileSelected}
          />
        </div>
        {filename && (
          <p className="mt-2 text-xs text-gray-500 truncate" title={filename}>
            File: {filename}
            {rows.length ? ` · ${rows.length} row${rows.length === 1 ? '' : 's'}` : ''}
          </p>
        )}
      </div>

      {(busy || enriching) && (
        <div className="flex items-center gap-2 text-sm text-[#1a7a9e]">
          <i className="fas fa-spinner fa-spin" aria-hidden="true" />
          {enriching ? 'AI is filling gaps…' : 'Working…'}
        </div>
      )}

      {fatalError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {fatalError}
        </div>
      )}

      {parseErrors.length > 0 && !fatalError && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <i className="fas fa-triangle-exclamation mr-1" aria-hidden="true" />
          {parseErrors.length} row(s) skipped
          {parseErrors[0] ? `: ${parseErrors[0]}` : ''}
        </div>
      )}

      {enrichSummary && (
        <div className="rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs text-cyan-900">
          <i className="fas fa-wand-magic-sparkles mr-1" aria-hidden="true" />
          {enrichSummary}
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3 space-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer select-none">
                <input
                  ref={selectAllRef}
                  type="checkbox"
                  checked={allSelected}
                  onChange={() => {
                    if (allSelected) setSelectedRowIndexes(new Set())
                    else setSelectedRowIndexes(new Set(rows.map((_, i) => i)))
                  }}
                  disabled={busy}
                  className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                />
                <span className="font-medium">Select all</span>
                <span className="text-gray-500">
                  ({selectedRowIndexes.size}/{rows.length})
                </span>
              </label>
              <label className="flex items-center gap-1.5 text-xs text-gray-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={fillEmptyOnly}
                  onChange={(e) => setFillEmptyOnly(e.target.checked)}
                  disabled={busy}
                  className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                />
                Only fill empty
              </label>
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <select
                value={bulkCommunityId}
                onChange={(e) => setBulkCommunityId(e.target.value)}
                disabled={busy || communitiesLoading || !selectableCommunities.length}
                className="flex-1 min-w-0 rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm"
                aria-label="Shared community"
              >
                <option value="">
                  {communitiesLoading ? 'Loading communities…' : 'One community for selected…'}
                </option>
                {selectableCommunities.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={applyCommunityToSelected}
                disabled={busy || !bulkCommunityId || !selectedRowIndexes.size}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40"
              >
                Apply community ({selectedRowIndexes.size})
              </button>
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                value={bulkLocation}
                onChange={(e) => setBulkLocation(e.target.value)}
                disabled={busy}
                placeholder="One pickup address for selected…"
                className="flex-1 min-w-0 rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm"
              />
              <button
                type="button"
                onClick={applyLocationToSelected}
                disabled={busy || !String(bulkLocation || '').trim() || !selectedRowIndexes.size}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40"
              >
                Apply address ({selectedRowIndexes.size})
              </button>
            </div>

            <div className="flex flex-col sm:flex-row gap-2">
              <select
                value={bulkCategory}
                onChange={(e) => setBulkCategory(e.target.value)}
                disabled={busy}
                className="flex-1 min-w-0 rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm"
              >
                <option value="">Category (optional)…</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <input
                type="date"
                value={bulkExpiry}
                onChange={(e) => setBulkExpiry(e.target.value)}
                disabled={busy}
                className="flex-1 min-w-0 rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm"
              />
              <button
                type="button"
                onClick={() => {
                  if (bulkCategory) applyCategoryToSelected()
                  if (bulkExpiry) applyExpiryToSelected()
                }}
                disabled={
                  busy
                  || !selectedRowIndexes.size
                  || (!bulkCategory && !bulkExpiry)
                }
                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40"
              >
                Apply
              </button>
            </div>

            <button
              type="button"
              onClick={applyAllMissingToSelected}
              disabled={
                busy
                || !selectedRowIndexes.size
                || (
                  !String(bulkCommunityId || '').trim()
                  && !String(bulkLocation || '').trim()
                  && !bulkCategory
                  && !bulkExpiry
                )
              }
              className="w-full px-3 py-2 rounded-lg text-xs font-semibold border border-cyan-300 bg-cyan-50 text-cyan-900 hover:bg-cyan-100 disabled:opacity-40"
            >
              {fillEmptyOnly
                ? `Apply all to empty fields (${selectedRowIndexes.size} rows)`
                : `Apply all to selected (${selectedRowIndexes.size})`}
            </button>
          </div>

          {communitiesError && (
            <div className="text-xs text-amber-700 flex items-center gap-2">
              <span>{communitiesError}</span>
              <button type="button" onClick={loadCommunities} className="underline">
                Retry
              </button>
            </div>
          )}

          <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
            {rows.map((row, idx) => (
              <div
                key={`bulk-row-${idx}`}
                className="rounded-xl border border-gray-200 bg-white p-3 flex gap-2 shadow-sm"
              >
                <input
                  type="checkbox"
                  checked={selectedRowIndexes.has(idx)}
                  onChange={() => {
                    setSelectedRowIndexes((prev) => {
                      const next = new Set(prev)
                      if (next.has(idx)) next.delete(idx)
                      else next.add(idx)
                      return next
                    })
                  }}
                  disabled={busy}
                  className="mt-1 rounded border-gray-300 text-emerald-600"
                  aria-label={`Select row ${idx + 1}`}
                />
                {row.image_url && (
                  <img
                    src={row.image_url}
                    alt=""
                    className="w-12 h-12 rounded-lg object-cover border border-gray-200 flex-shrink-0"
                    onError={(e) => { e.target.style.display = 'none' }}
                  />
                )}
                <div className="flex-1 min-w-0 space-y-1.5">
                  <input
                    type="text"
                    value={row.title || ''}
                    onChange={(e) => updateRow(idx, { title: e.target.value })}
                    disabled={busy}
                    className="w-full text-sm font-medium border border-gray-200 rounded-md px-2 py-1"
                    aria-label={`Row ${idx + 1} title`}
                  />
                  <div className="flex flex-wrap gap-1.5 text-xs">
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      value={row.quantity ?? ''}
                      onChange={(e) => updateRow(idx, { quantity: Number(e.target.value) })}
                      disabled={busy}
                      className="w-16 border border-gray-200 rounded-md px-1.5 py-1"
                      aria-label="Quantity"
                    />
                    <input
                      type="text"
                      value={row.unit || ''}
                      onChange={(e) => updateRow(idx, { unit: e.target.value })}
                      disabled={busy}
                      className="w-16 border border-gray-200 rounded-md px-1.5 py-1"
                      aria-label="Unit"
                    />
                    <select
                      value={row.category || 'other'}
                      onChange={(e) => updateRow(idx, { category: e.target.value })}
                      disabled={busy}
                      className="border border-gray-200 rounded-md px-1.5 py-1"
                      aria-label="Category"
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-1.5 text-xs">
                    <input
                      type="text"
                      value={row.location || ''}
                      onChange={(e) => updateRow(idx, { location: e.target.value })}
                      disabled={busy}
                      placeholder="Pickup address"
                      className="border border-gray-200 rounded-md px-1.5 py-1"
                    />
                    <input
                      type="date"
                      value={row.expiry_date || ''}
                      onChange={(e) => updateRow(idx, { expiry_date: e.target.value })}
                      disabled={busy}
                      className="border border-gray-200 rounded-md px-1.5 py-1"
                    />
                    <select
                      value={row.community_id || ''}
                      onChange={(e) => {
                        const id = e.target.value || ''
                        const match = selectableCommunities.find((c) => String(c.id) === String(id))
                        updateRow(idx, {
                          community_id: id || undefined,
                          community_name: match?.name,
                        })
                      }}
                      disabled={busy || communitiesLoading}
                      className={`border rounded-md px-1.5 py-1 ${
                        row.community_id ? 'border-gray-200' : 'border-amber-400'
                      }`}
                      required
                    >
                      <option value="">Choose school or community…</option>
                      {selectableCommunities.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeRow(idx)}
                  disabled={busy}
                  className="text-gray-400 hover:text-rose-500 self-start p-1 disabled:opacity-40"
                  aria-label={`Remove row ${idx + 1}`}
                >
                  <i className="fas fa-times" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>

          {missingCommunity && (
            <div className="text-sm text-amber-700">
              <i className="fas fa-triangle-exclamation mr-1" aria-hidden="true" />
              Choose a school or community for each row (use Apply community above to set them all at once).
            </div>
          )}

          {apiErrors.length > 0 && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 space-y-1">
              {apiErrors.map((err, i) => (
                <div key={i}>
                  {typeof err === 'string'
                    ? err
                    : (err?.error || err?.message || JSON.stringify(err))}
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              onClick={reset}
              disabled={busy}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={busy || enriching || !rows.length || missingCommunity}
              className="px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 shadow-sm"
            >
              {busy ? 'Publishing…' : `Publish ${rows.length} listing${rows.length === 1 ? '' : 's'}`}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

ShareBulkCsvPanel.propTypes = {
  userId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  preferredCommunityId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  preferredLocation: PropTypes.string,
  lockToUserCommunity: PropTypes.bool,
  onSuccess: PropTypes.func,
}

export default ShareBulkCsvPanel
