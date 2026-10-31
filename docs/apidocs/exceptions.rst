=======================
Exceptions and warnings
=======================

All Coheriq exceptions derive from :exc:`~coheriq.CoheriqError`.

.. autoexception:: coheriq.CoheriqError
.. autoexception:: coheriq.CoheriqLibraryError
.. autoexception:: coheriq.CoheriqDomainError
.. autoexception:: coheriq.CoheriqEngineError
.. autoexception:: coheriq.CoheriqEngineInheritanceError
.. autoexception:: coheriq.CoheriqUserError
.. autoexception:: coheriq.CoheriqDomainNotFoundError
.. autoexception:: coheriq.CoheriqEngineNotFoundError

Warnings
========

All Coheriq warnings derive from :exc:`~coheriq.CoheriqWarning`, which derives
from :exc:`UserWarning`, so they can be filtered as a group.

.. autoexception:: coheriq.CoheriqWarning
.. autoexception:: coheriq.CoheriqDomainWarning
