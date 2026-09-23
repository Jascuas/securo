import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, within } from '@testing-library/react'

import ProductsPage from '@/pages/products'
import { InvoiceLineEditor } from '@/components/invoice-line-editor'
import { renderWithProviders, t } from '@/test/utils'
import type { InvoiceLineInput, Product } from '@/types'

const api = vi.hoisted(() => ({
  products: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    addPrice: vi.fn(),
    updatePrice: vi.fn(),
    removePrice: vi.fn(),
  },
  invoices: { settings: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  products: api.products,
  invoices: api.invoices,
}))

vi.mock('@/hooks/use-display-locale', () => ({
  useDisplayLocale: () => 'en-US',
  useDateLocale: () => 'en-US',
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuth: () => ({ user: { preferences: { currency_display: 'USD' } } }),
}))

let canWrite = true
vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ canWrite }),
}))

vi.mock('@/hooks/use-privacy-mode', () => ({
  usePrivacyMode: () => ({ mask: (value: string) => value }),
}))

function product(overrides: Partial<Product> = {}): Product {
  return {
    id: 'hour',
    name: 'Consulting hour',
    description: 'Senior engineer',
    kind: 'service',
    unit: 'h',
    active: true,
    origin: 'local',
    external_source: null,
    external_id: null,
    custom_fields: null,
    prices: [
      {
        id: 'usd', product_id: 'hour', currency: 'USD', unit_price: '200.00', tax_rate: null,
        billing: 'one_time', interval: null, nickname: null, active: true,
        external_source: null, external_id: null, created_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'eur', product_id: 'hour', currency: 'EUR', unit_price: '900.00', tax_rate: null,
        billing: 'recurring', interval: 'monthly', nickname: 'Monthly', active: true,
        external_source: null, external_id: null, created_at: '2026-01-02T00:00:00Z',
      },
    ],
    created_at: '2026-01-01T00:00:00Z',
    invoice_count: 3,
    ...overrides,
  }
}

describe('ProductsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    canWrite = true
    api.products.list.mockResolvedValue([
      product(),
      product({ id: 'logo', name: 'Logo design', kind: 'product', description: null, unit: null, prices: [], invoice_count: 0 }),
    ])
    api.invoices.settings.mockResolvedValue({ tax_fields: 'hidden' })
  })

  it('lists the catalog with every live price and what each product is worth to invoices', async () => {
    renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    const rows = await screen.findAllByTestId('product-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Consulting hour')).toBeInTheDocument()
    expect(within(rows[0]).getByText(t('invoices.products.kind.service'))).toBeInTheDocument()
    expect(within(rows[0]).getByText('$200.00 · €900.00 / month')).toBeInTheDocument()
    expect(within(rows[0]).getByText('3')).toBeInTheDocument()
    expect(within(rows[1]).getByText(t('invoices.products.noPrice'))).toBeInTheDocument()
    expect(api.products.list).toHaveBeenLastCalledWith({ active: true })
  })

  it('offers archive to a named product and delete only to an unnamed one', async () => {
    renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    const rows = await screen.findAllByTestId('product-row')
    expect(within(rows[0]).getByLabelText(t('invoices.products.action.archive'))).toBeInTheDocument()
    expect(within(rows[0]).queryByLabelText(t('common.delete'))).not.toBeInTheDocument()
    expect(within(rows[1]).getByLabelText(t('common.delete'))).toBeInTheDocument()
  })

  it('switches to the archived list through the server', async () => {
    const { user } = renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    await screen.findAllByTestId('product-row')
    await user.click(screen.getByTestId('product-filter-archived'))
    expect(api.products.list).toHaveBeenLastCalledWith({ active: false })
  })

  it('hides every write from a viewer', async () => {
    canWrite = false
    renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    await screen.findAllByTestId('product-row')
    expect(screen.queryByTestId('product-new-button')).not.toBeInTheDocument()
    expect(screen.queryByLabelText(t('common.edit'))).not.toBeInTheDocument()
  })

  it('creates a product with its prices in one call', async () => {
    api.products.create.mockResolvedValue(product())
    const { user } = renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    await screen.findAllByTestId('product-row')
    await user.click(screen.getByTestId('product-new-button'))
    await screen.findByTestId('product-name-input')
    expect(screen.getByTestId('product-save')).toBeDisabled()
    await user.type(screen.getByTestId('product-name-input'), 'Retainer')
    await user.type(screen.getByTestId('product-unit-input'), 'month')
    await user.type(screen.getByTestId('price-amount-0'), '3000')
    await user.click(screen.getByTestId('product-save'))
    expect(api.products.create).toHaveBeenCalledWith({
      name: 'Retainer',
      kind: 'service',
      unit: 'month',
      description: null,
      prices: [{ currency: 'USD', unit_price: '3000', tax_rate: null, billing: 'one_time', interval: null, nickname: null }],
    })
  })
})

describe('ProductsPage editing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    canWrite = true
    api.products.list.mockResolvedValue([product()])
    api.invoices.settings.mockResolvedValue({ tax_fields: 'hidden' })
    api.products.update.mockResolvedValue(product())
    api.products.updatePrice.mockResolvedValue(product())
  })

  it('archives an existing price instead of deleting it, and never deletes from the dialog', async () => {
    const { user } = renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    const [row] = await screen.findAllByTestId('product-row')
    await user.click(within(row).getByLabelText(t('common.edit')))
    await screen.findByTestId('product-name-input')
    await user.click(screen.getByTestId('price-archive-1'))
    expect(screen.getByTestId('price-restore-1')).toBeInTheDocument()
    await user.click(screen.getByTestId('product-save'))
    expect(api.products.removePrice).not.toHaveBeenCalled()
    expect(api.products.updatePrice).toHaveBeenCalledWith('hour', 'eur', expect.objectContaining({ active: false }))
    expect(api.products.updatePrice).toHaveBeenCalledWith('hour', 'usd', expect.objectContaining({ active: true }))
  })

  it('closes on the server state when a request in the sequence fails', async () => {
    api.products.updatePrice.mockRejectedValueOnce({ response: { data: { detail: { code: 'negative_price' } } } })
    const { user } = renderWithProviders(<ProductsPage />, { route: '/invoices/products' })
    const [row] = await screen.findAllByTestId('product-row')
    await user.click(within(row).getByLabelText(t('common.edit')))
    await screen.findByTestId('product-name-input')
    await user.click(screen.getByTestId('product-save'))
    await screen.findAllByTestId('product-row')
    expect(screen.queryByTestId('product-name-input')).not.toBeInTheDocument()
  })
})

describe('InvoiceLineEditor with the catalog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.products.list.mockResolvedValue([product()])
  })

  function Harness({ currency, initial }: { currency: string; initial: InvoiceLineInput[] }) {
    const [lines, setLines] = useState<InvoiceLineInput[]>(initial)
    return <InvoiceLineEditor lines={lines} onChange={setLines} currency={currency} showTax={false} required />
  }

  it('fills the line from the product at the price in the invoice currency, and marks it', async () => {
    const { user } = renderWithProviders(<Harness currency="USD" initial={[{ description: '', quantity: '2', unit_price: '0' }]} />)
    await user.click(screen.getByTestId('invoice-line-pick-product'))
    await user.click(await screen.findByTestId('product-option-hour'))
    expect(screen.getByTestId('invoice-line-description-0')).toHaveValue('Consulting hour')
    expect(screen.getByTestId('invoice-line-unit-0')).toHaveValue('h')
    expect(screen.getByTestId('invoice-line-price-0')).toHaveValue('200.00')
    expect(screen.getByTestId('invoice-line-quantity-0')).toHaveValue('2')
    expect(screen.getByTestId('invoice-line-amount-0')).toHaveTextContent('$400.00')
    expect(screen.getByTestId('invoice-line-from-catalog-0')).toBeInTheDocument()
  })

  it('fills only the name when the product has no price in the currency', async () => {
    const { user } = renderWithProviders(<Harness currency="BRL" initial={[{ description: '', quantity: '1', unit_price: '50' }]} />)
    await user.click(screen.getByTestId('invoice-line-pick-product'))
    const option = await screen.findByTestId('product-option-hour')
    expect(option).toHaveTextContent(t('invoices.products.noPriceIn', { currency: 'BRL' }))
    await user.click(option)
    expect(screen.getByTestId('invoice-line-description-0')).toHaveValue('Consulting hour')
    expect(screen.getByTestId('invoice-line-price-0')).toHaveValue('50')
  })
})
