
-- Base de datos TechSolutions
-- Tabla de citas medicas

CREATE TABLE IF NOT EXISTS citas (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(50) NOT NULL,
    fecha TIMESTAMP NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    creada_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indice para mejorar las consultas por fecha
CREATE INDEX IF NOT EXISTS idx_citas_fecha
ON citas(fecha);

-- Datos de prueba sin informacion personal
INSERT INTO citas (tipo, fecha, estado)
VALUES
    ('Revision general', '2026-12-01 10:00:00', 'pendiente'),
    ('Consulta preventiva', '2026-12-02 11:30:00', 'confirmada'),
    ('Revision anual', '2026-12-03 09:00:00', 'pendiente');
