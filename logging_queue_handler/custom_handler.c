/*
 * Custom Logging Handler C Extension
 * ===================================
 * 
 * A high-performance C extension for Python logging.
 * Demonstrates integration with QueueHandler and QueueListener.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <structmember.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    PyObject_HEAD
    char *filename;
    FILE *fp;
    int level;
    int buffer_size;
    PyObject *buffer;
    int delay;
} CustomHandlerObject;

static PyObject* get_timestamp(void) {
    time_t now;
    struct tm *tm_info;
    char buffer[64];
    
    time(&now);
    tm_info = localtime(&now);
    strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", tm_info);
    
    return PyUnicode_FromString(buffer);
}

static PyObject* format_record(PyObject *record) {
    PyObject *getMessage = PyObject_GetAttrString(record, "getMessage");
    PyObject *result = NULL;
    
    if (getMessage && PyCallable_Check(getMessage)) {
        result = PyObject_CallObject(getMessage, NULL);
    } else {
        PyErr_Clear();
        result = PyObject_Str(record);
    }
    
    Py_XDECREF(getMessage);
    return result;
}

static int write_to_file(CustomHandlerObject *self, const char *message) {
    if (self->fp) {
        size_t len = strlen(message);
        fwrite(message, 1, len, self->fp);
        fputc('\n', self->fp);
        fflush(self->fp);
        return 0;
    }
    return -1;
}

static int CustomHandler_init(CustomHandlerObject *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"filename", "level", "buffer_size", "delay", NULL};
    PyObject *filename = NULL;
    PyObject *level_obj = NULL;
    int buffer_size = 100;
    int delay = 0;
    
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|Oii", kwlist,
                                     &filename, &level_obj, &buffer_size, &delay)) {
        return -1;
    }
    
    const char *filename_str = PyUnicode_AsUTF8(filename);
    if (!filename_str) {
        PyErr_SetString(PyExc_TypeError, "filename must be a string");
        return -1;
    }
    
    self->filename = strdup(filename_str);
    if (!self->filename) {
        PyErr_SetString(PyExc_MemoryError, "Failed to allocate memory");
        return -1;
    }
    
    self->level = (level_obj && PyLong_Check(level_obj)) ? PyLong_AsLong(level_obj) : 10;
    self->buffer_size = (buffer_size > 0) ? buffer_size : 100;
    self->delay = (delay >= 0 && delay <= 10000) ? delay : 0;
    
    self->buffer = PyList_New(0);
    if (!self->buffer) {
        free(self->filename);
        return -1;
    }
    
    self->fp = fopen(self->filename, "a");
    if (!self->fp) {
        PyErr_SetFromErrnoWithFilename(PyExc_IOError, self->filename);
        Py_DECREF(self->buffer);
        free(self->filename);
        self->filename = NULL;
        return -1;
    }
    
    return 0;
}

static PyObject* CustomHandler_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    CustomHandlerObject *self = (CustomHandlerObject *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->filename = NULL;
        self->fp = NULL;
        self->level = 10;
        self->buffer_size = 100;
        self->buffer = NULL;
        self->delay = 0;
    }
    return (PyObject *)self;
}

static void CustomHandler_dealloc(CustomHandlerObject *self) {
    if (self->fp) {
        fclose(self->fp);
        self->fp = NULL;
    }
    if (self->filename) {
        free(self->filename);
        self->filename = NULL;
    }
    Py_XDECREF(self->buffer);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject* CustomHandler_emit(CustomHandlerObject *self, PyObject *record) {
    PyObject *levelname = PyObject_GetAttrString(record, "levelname");
    PyObject *logger_name = PyObject_GetAttrString(record, "name");
    PyObject *formatted_msg = format_record(record);
    PyObject *timestamp = get_timestamp();
    
    const char *level_str = levelname ? PyUnicode_AsUTF8(levelname) : "UNKNOWN";
    const char *logger_str = logger_name ? PyUnicode_AsUTF8(logger_name) : "root";
    const char *msg_str = formatted_msg ? PyUnicode_AsUTF8(formatted_msg) : "<error>";
    
    char output[8192];
    snprintf(output, sizeof(output), "[%s] [%s] [%s] %s",
             PyUnicode_AsUTF8(timestamp),
             level_str,
             logger_str,
             msg_str);
    
    write_to_file(self, output);
    
    Py_XDECREF(levelname);
    Py_XDECREF(logger_name);
    Py_XDECREF(formatted_msg);
    Py_XDECREF(timestamp);
    
    Py_RETURN_NONE;
}

static PyObject* CustomHandler_flush(CustomHandlerObject *self) {
    if (self->fp) fflush(self->fp);
    Py_RETURN_NONE;
}

static PyObject* CustomHandler_close(CustomHandlerObject *self) {
    if (self->fp) {
        fclose(self->fp);
        self->fp = NULL;
    }
    Py_RETURN_NONE;
}

static PyObject* CustomHandler_get_stats(CustomHandlerObject *self) {
    PyObject *result = PyDict_New();
    PyDict_SetItemString(result, "filename", PyUnicode_FromString(self->filename ?: ""));
    PyDict_SetItemString(result, "level", PyLong_FromLong(self->level));
    PyDict_SetItemString(result, "buffer_size", PyLong_FromLong(self->buffer_size));
    return result;
}

static PyMethodDef CustomHandler_methods[] = {
    {"emit", (PyCFunction)CustomHandler_emit, METH_O, "Emit a log record"},
    {"flush", (PyCFunction)CustomHandler_flush, METH_NOARGS, "Flush output"},
    {"close", (PyCFunction)CustomHandler_close, METH_NOARGS, "Close handler"},
    {"get_stats", (PyCFunction)CustomHandler_get_stats, METH_NOARGS, "Get statistics"},
    {NULL}
};

static PyTypeObject CustomHandlerType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "custom_handler.CustomHandler",
    sizeof(CustomHandlerObject),
    0,
    (destructor)CustomHandler_dealloc,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    CustomHandler_methods,
    0,
    CustomHandler_init,
    CustomHandler_new,
};

/* Module definition */
static PyMethodDef module_methods[] = {
    {NULL}
};

static struct PyModuleDef custom_handler_module = {
    PyModuleDef_HEAD_INIT,
    "custom_handler",
    "High-performance C extension logging handler",
    -1,
    module_methods
};

PyMODINIT_FUNC PyInit_custom_handler(void) {
    PyObject *module = PyModule_Create(&custom_handler_module);
    if (module == NULL) return NULL;
    
    CustomHandlerType.tp_new = CustomHandler_new;
    if (PyType_Ready(&CustomHandlerType) < 0) return NULL;
    
    Py_INCREF(&CustomHandlerType);
    PyModule_AddObject(module, "CustomHandler", (PyObject *)&CustomHandlerType);
    
    return module;
}
