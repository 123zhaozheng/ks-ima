import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import PdfPreview from '../../src/components/PdfPreview.vue'

const state = vi.hoisted(() => ({
  getDocument: vi.fn(),
  documentDestroy: vi.fn(),
  taskDestroy: vi.fn(),
}))

vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({
  getDocument: state.getDocument,
  GlobalWorkerOptions: { workerSrc: '' },
}))

type Deferred<T> = {
  promise: Promise<T>
  resolve: (value: T | PromiseLike<T>) => void
  reject: (reason?: unknown) => void
}

function deferred<T>(): Deferred<T> {
  let resolveDeferred!: Deferred<T>['resolve']
  let rejectDeferred!: Deferred<T>['reject']
  const promise = new Promise<T>((resolve, reject) => {
    resolveDeferred = resolve
    rejectDeferred = reject
  })
  return { promise, resolve: resolveDeferred, reject: rejectDeferred }
}

function loadingTask(promise: Promise<unknown>) {
  return { promise, destroy: state.taskDestroy }
}

function renderTask(promise: Promise<void>, cancel = vi.fn()) {
  return { promise, cancel }
}

function pageFor(task = renderTask(Promise.resolve())) {
  const viewport = { width: 100, height: 200 }
  return {
    getViewport: vi.fn().mockReturnValue(viewport),
    render: vi.fn().mockReturnValue(task),
  }
}

function documentFor(page: ReturnType<typeof pageFor>, numPages = 1) {
  return {
    numPages,
    getPage: vi.fn().mockResolvedValue(page),
    destroy: state.documentDestroy,
  }
}

function mountPdf(src = '/documents/test.pdf') {
  return mount(PdfPreview, {
    props: { src, title: 'test.pdf' },
    global: { stubs: { 'q-spinner': { template: '<span />' } } },
  })
}

describe('PdfPreview lifecycle', () => {
  beforeEach(() => {
    state.getDocument.mockReset()
    state.documentDestroy.mockReset().mockResolvedValue(undefined)
    state.taskDestroy.mockReset().mockResolvedValue(undefined)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as CanvasRenderingContext2D)
  })

  test('loads a page and completes its canvas render', async () => {
    const page = pageFor()
    const pdfDocument = documentFor(page)
    state.getDocument.mockReturnValue(loadingTask(Promise.resolve(pdfDocument)))
    const wrapper = mountPdf()

    await flushPromises()

    expect(state.getDocument).toHaveBeenCalledWith({
      url: '/documents/test.pdf',
      isEvalSupported: false,
    })
    expect(pdfDocument.getPage).toHaveBeenCalledWith(1)
    expect(page.render).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.pdf-preview-page')).toHaveLength(1)
    expect(wrapper.find('canvas').exists()).toBe(true)
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)

    wrapper.unmount()
    await flushPromises()
  })

  test('shows an error when the worker cannot load the document', async () => {
    const workerError = new Error('worker failed')
    state.getDocument.mockReturnValue(loadingTask(Promise.reject(workerError)))
    const wrapper = mountPdf()

    await flushPromises()

    expect(wrapper.find('[role="alert"]').text()).toContain('PDF 加载失败')
    expect(wrapper.emitted('error')).toEqual([[workerError]])
    expect(state.taskDestroy).toHaveBeenCalledTimes(1)
  })

  test('shows an error for a corrupt PDF', async () => {
    const invalidPdfError = Object.assign(new Error('Invalid PDF'), { name: 'InvalidPDFException' })
    state.getDocument.mockReturnValue(loadingTask(Promise.reject(invalidPdfError)))
    const wrapper = mountPdf()

    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.emitted('error')).toEqual([[invalidPdfError]])
    expect(state.taskDestroy).toHaveBeenCalledTimes(1)
  })

  test('shows an error when page rendering fails', async () => {
    const renderError = new Error('render failed')
    const page = pageFor(renderTask(Promise.reject(renderError)))
    const pdfDocument = documentFor(page)
    state.getDocument.mockReturnValue(loadingTask(Promise.resolve(pdfDocument)))
    const wrapper = mountPdf()

    await flushPromises()

    expect(pdfDocument.getPage).toHaveBeenCalledWith(1)
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.emitted('error')).toEqual([[renderError]])
  })

  test('cancels stale rendering when src changes', async () => {
    const firstRender = deferred<void>()
    const firstRenderTask = renderTask(firstRender.promise)
    firstRenderTask.cancel.mockImplementation(() => firstRender.reject(new Error('cancelled')))
    const firstPage = pageFor(firstRenderTask)
    const firstDocument = documentFor(firstPage)
    const secondPage = pageFor()
    const secondDocument = documentFor(secondPage)
    state.getDocument
      .mockReturnValueOnce(loadingTask(Promise.resolve(firstDocument)))
      .mockReturnValueOnce(loadingTask(Promise.resolve(secondDocument)))
    const wrapper = mountPdf('/documents/first.pdf')

    await flushPromises()
    expect(firstPage.render).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ src: '/documents/second.pdf' })
    await flushPromises()

    expect(firstRenderTask.cancel).toHaveBeenCalledTimes(1)
    expect(secondDocument.getPage).toHaveBeenCalledWith(1)
    expect(wrapper.findAll('.pdf-preview-page')).toHaveLength(1)
    expect(wrapper.emitted('error')).toBeUndefined()

    wrapper.unmount()
    await flushPromises()
  })

  test('destroys a loading task when unmounted before the document loads', async () => {
    const pendingDocument = deferred<unknown>()
    state.getDocument.mockReturnValue(loadingTask(pendingDocument.promise))
    const wrapper = mountPdf()

    await flushPromises()
    wrapper.unmount()

    expect(state.taskDestroy).toHaveBeenCalledTimes(1)
    pendingDocument.resolve({})
    await flushPromises()
  })

  test('cancels rendering and destroys the document when unmounted', async () => {
    const pendingRender = deferred<void>()
    const activeRenderTask = renderTask(pendingRender.promise)
    activeRenderTask.cancel.mockImplementation(() => pendingRender.reject(new Error('unmounted')))
    const page = pageFor(activeRenderTask)
    const pdfDocument = documentFor(page)
    state.getDocument.mockReturnValue(loadingTask(Promise.resolve(pdfDocument)))
    const wrapper = mountPdf()

    await flushPromises()
    wrapper.unmount()
    await flushPromises()

    expect(activeRenderTask.cancel).toHaveBeenCalledTimes(1)
    expect(state.documentDestroy).toHaveBeenCalledTimes(1)
  })
})

export {}
