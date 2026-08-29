"""Contenido del cuaderno del profesor (orden e índice alineados con el PDF oficial)."""

from __future__ import annotations

# Cada sección: id, título, body (texto plano). Opcional body_html para formato en pantalla.
CUADERNO_SECTIONS: list[dict[str, str]] = [
    {
        "id": "horarios-contacto",
        "title": "1. Horarios y contacto",
        "body": """HORARIO DEL CENTRO: de 08:35 a 14:30
o Recreo: 11:20-11:50
TARDES
o LUNES Y MARTES: de 16:30 a 18:10
o JUEVES: de 16:30 a 19:50
TELÉFONO: 987 252 198
http://iesantoniogarciabellido.centros.educa.jcyl.es/sitio/
https://www.instagram.com/iesantoniogarciabellido/?hl=es
https://www.facebook.com/people/Antonio-Garcia-Bellido/100009154981416""",
        "body_html": """<div class="cuaderno-hc">
<p class="cuaderno-hc-line">HORARIO DEL CENTRO: de 08:35 a 14:30</p>
<p class="cuaderno-hc-indent">o Recreo: 11:20-11:50</p>
<p class="cuaderno-hc-line">TARDES</p>
<p class="cuaderno-hc-indent">o LUNES Y MARTES: de 16:30 a 18:10</p>
<p class="cuaderno-hc-indent">o JUEVES: de 16:30 a 19:50</p>
<p class="cuaderno-hc-phone">TELÉFONO: 987 252 198</p>
<p class="cuaderno-hc-links">
<a href="http://iesantoniogarciabellido.centros.educa.jcyl.es/sitio/" target="_blank" rel="noopener noreferrer">http://iesantoniogarciabellido.centros.educa.jcyl.es/sitio/</a><br>
<a href="https://www.instagram.com/iesantoniogarciabellido/?hl=es" target="_blank" rel="noopener noreferrer">https://www.instagram.com/iesantoniogarciabellido/?hl=es</a><br>
<a href="https://www.facebook.com/people/Antonio-Garcia-Bellido/100009154981416" target="_blank" rel="noopener noreferrer">https://www.facebook.com/people/Antonio-Garcia-Bellido/100009154981416</a>
</p>
</div>""",
    },
    {
        "id": "permisos",
        "title": "2. Solicitud de permisos",
        "subtitle": "ES OBLIGATORIO hacer DOS TRÁMITES",
        "body": """1. Aviso en Jefatura.

* Anexo II:  Se comunica en Jefatura de Estudios el día y la hora de la falta en cuanto se tenga conocimiento de la misma para que lo tengan en cuenta a la hora de elaborar el parte de guardias.

* Anexo I: Se comunica en Jefatura de Estudios el día que se quiere solicitar para que nos apunten en el calendario que se encuentra en el corcho de Jefatura de Estudios. NO SE PUEDE SOLICITAR NINGÚN MOSCOSO SIN HABERSE APUNTADO PREVIAMENTE EN ESTE CALENDARIO.

2. Solicitud a la Directora.

* Rellenar el anexo correspondiente, firmado DIGITALMENTE, con el CERTIFICADO ELECTRÓNICO, dejar el documento abierto para que pueda ser firmado por la Directora (o en el caso del Anexo I al Director Provincial).

* Nombrarlo con los siguientes datos: APELLIDOS, NOMBRE – CENTRO – FECHA Ejemplo: FAJARDO LÓPEZ, ANTONIO – IES ANTONIO GARCÍA BELLIDO – 09-09-2026.

* Enviarlo a la dirección de correo electrónico permisos.bellido@gmail.com

Solicitudes Anexo II:

* El envío de las solicitudes (anexo II) debe ser anterior al disfrute del permiso (salvo en el caso de enfermedad sobrevenida. Disponemos de cuatro días al año de este tipo de faltas, tres consecutivos). Si no se responde en el plazo de dos días es que el permiso está concedido.

* Se enviarán los justificantes escaneados una vez se disponga de los mismos al email en el que se solicitó el permiso.
o En caso de no disponer de dicho justificante porque la falta es por haberse puesto enfermo y no haber asistido a ninguna consulta médica, se enviará el permiso sin este justificante.
o Se adjuntará el justificante escaneado una vez se disponga del documento, CONTESTANDO AL MENSAJE PREVIAMENTE ENVIADO SOLICITANDO EL PERMISO.

* El permiso por consulta médica propia o de acompañante es por el TIEMPO IMPRESCINDIBLE.

Solicitudes Anexo I:

* La concesión del Moscoso está sujeta a la organización del centro y por ello seguimos los siguientes criterios: - Se conceden dos moscosos al día. - No se conceden moscosos en los días señalados en la Orden ni en los coincidentes con las pruebas de EBAU ni si hubiera una actividad extraescolar esos días.

* La solicitud ha de ser enviada entre quince y siete días antes de ser disfrutado. SI NO SE ENVÍA EN PLAZO LA SOLICITUD PARA PEDIR EL PERMISO, NO PODRÁ SER TRAMITADA Y POR TANTO NO SE PODRÁ DISFRUTAR DEL MOSCOSO.

* La solicitud del Moscoso (Anexo I) se rellena con los datos y se marca la última casilla "Otros". En el apartado de "Observaciones" se señala "Asunto de interés particular". El envío de la documentación del moscoso se hace a través de la plataforma.

IMPORTANTE: NO CERRAR EL DOCUMENTO DESPUÉS DE FIRMARLO DIGITALMENTE PARA QUE PUEDA SER FIRMADO POSTERIORMENTE.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-title">1. Aviso en Jefatura.</p>
<p class="cuaderno-perm-star">* Anexo II:  Se comunica en Jefatura de Estudios el día y la hora de la falta en cuanto se tenga conocimiento de la misma para que lo tengan en cuenta a la hora de elaborar el parte de guardias.</p>
<p class="cuaderno-perm-star">* Anexo I: Se comunica en Jefatura de Estudios el día que se quiere solicitar para que nos apunten en el calendario que se encuentra en el corcho de Jefatura de Estudios. NO SE PUEDE SOLICITAR NINGÚN MOSCOSO SIN HABERSE APUNTADO PREVIAMENTE EN ESTE CALENDARIO.</p>
<p class="cuaderno-perm-title">2. Solicitud a la Directora.</p>
<p class="cuaderno-perm-star">* Rellenar el anexo correspondiente, firmado DIGITALMENTE, con el CERTIFICADO ELECTRÓNICO, dejar el documento abierto para que pueda ser firmado por la Directora (o en el caso del Anexo I al Director Provincial).</p>
<p class="cuaderno-perm-star">* Nombrarlo con los siguientes datos: APELLIDOS, NOMBRE – CENTRO – FECHA Ejemplo: FAJARDO LÓPEZ, ANTONIO – IES ANTONIO GARCÍA BELLIDO – 09-09-2026.</p>
<p class="cuaderno-perm-star">* Enviarlo a la dirección de correo electrónico permisos.bellido@gmail.com</p>
<p class="cuaderno-perm-subtitle">Solicitudes Anexo II:</p>
<p class="cuaderno-perm-star">* El envío de las solicitudes (anexo II) debe ser anterior al disfrute del permiso (salvo en el caso de enfermedad sobrevenida. Disponemos de cuatro días al año de este tipo de faltas, tres consecutivos). Si no se responde en el plazo de dos días es que el permiso está concedido.</p>
<p class="cuaderno-perm-star">* Se enviarán los justificantes escaneados una vez se disponga de los mismos al email en el que se solicitó el permiso.</p>
<p class="cuaderno-perm-sub">o En caso de no disponer de dicho justificante porque la falta es por haberse puesto enfermo y no haber asistido a ninguna consulta médica, se enviará el permiso sin este justificante.</p>
<p class="cuaderno-perm-sub">o Se adjuntará el justificante escaneado una vez se disponga del documento, CONTESTANDO AL MENSAJE PREVIAMENTE ENVIADO SOLICITANDO EL PERMISO.</p>
<p class="cuaderno-perm-star">* El permiso por consulta médica propia o de acompañante es por el TIEMPO IMPRESCINDIBLE.</p>
<p class="cuaderno-perm-subtitle">Solicitudes Anexo I:</p>
<p class="cuaderno-perm-star">* La concesión del Moscoso está sujeta a la organización del centro y por ello seguimos los siguientes criterios: - Se conceden dos moscosos al día. - No se conceden moscosos en los días señalados en la Orden ni en los coincidentes con las pruebas de EBAU ni si hubiera una actividad extraescolar esos días.</p>
<p class="cuaderno-perm-star">* La solicitud ha de ser enviada entre quince y siete días antes de ser disfrutado. SI NO SE ENVÍA EN PLAZO LA SOLICITUD PARA PEDIR EL PERMISO, NO PODRÁ SER TRAMITADA Y POR TANTO NO SE PODRÁ DISFRUTAR DEL MOSCOSO.</p>
<p class="cuaderno-perm-star">* La solicitud del Moscoso (Anexo I) se rellena con los datos y se marca la última casilla "Otros". En el apartado de "Observaciones" se señala "Asunto de interés particular". El envío de la documentación del moscoso se hace a través de la plataforma.</p>
<p class="cuaderno-perm-importante">IMPORTANTE: NO CERRAR EL DOCUMENTO DESPUÉS DE FIRMARLO DIGITALMENTE PARA QUE PUEDA SER FIRMADO POSTERIORMENTE.</p>
</div>""",
    },
    {
        "id": "guardias",
        "title": "3. Guardias",
        "body": """* La guardia se inicia con el primer timbre, es decir, a las 8:35 la de primera hora, a las 9:30 la de segunda y así sucesivamente cada una de las horas.
o Al iniciarse la guardia con el primer timbre facilita que si algún compañero tiene que salir del aula antes del segundo timbre porque tenga clase en la hora siguiente, los alumnos no permanecen solos en el aula.

* La guardia de cuarta hora se inicia a las 11:45 para estar en los pasillos cuando los alumnos vayan subiendo del patio y entrando de la calle.

* Pedimos colaboración a los profesores que imparten clase en 1º y en 2º de ESO para que se queden en el aula con los alumnos hasta que llegue el profesor de la siguiente hora. o Si tienen clase en la hora siguiente, pueden esperar a que el profesor de guardia llegue para la guardia de cambio de hora para ir a su clase.

* Los periodos de guardia se realizarán por turnos entre los profesores de guardia en los pasillos y en la sala de profesores siempre y cuando no haya guardias de aula que cubrir por ausencias de profesores.

* Los profesores de guardia deben comprobar las ausencias de compañeros cuando lleguen al centro para organizar los turnos de guardia tanto en las clases como en los pasillos.

* Los profesores que cubran las guardias de aula no podrán rotar en la misma hora con otros compañeros; se podrá rotar semanalmente, si los profesores que realizan la guardia en la misma hora así lo deciden. Sí se podrá rotar el turno de guardia por el pasillo en la misma hora si los profesores así lo acuerdan.

* Se establecen turnos de guardia por el pasillo, uno por el de 1º y 3º de ESO y por los pasillos de CFGB y CFGM. Y otro turno por el pasillo de 2º y 4º de ESO.

* Para realizar las guardias de patio, se establece un turno rotatorio entre los profesores de tal manera que uno vigile los accesos al baño y los otros el respeto de las zonas asignadas a cada grupo en el patio.
o Los profesores de patio controlarán además la organización de los turnos para que los alumnos vayan al baño (no más de dos alumnos a la vez).

* El profesor de pasillo se encargará de vigilar los pasillos y las aulas al inicio del recreo para evitar que el alumnado permanezca dentro de las clases y los alumnos que deben salir a la calle (a partir de 3º de ESO) permanezcan dentro del centro.
o Además, se encargan de organizar el uso de baños por parte de los alumnos que suben del patio para poder ir.

* Uno de los profesores que se encuentre de guardia de pasillo se encargará de revisar si los alumnos que salen a la calle son los que tienen permiso para ello (se les ha entregado un carné de color rojo a los alumnos de 1º y 2º de ESO porque no pueden salir a la calle durante el recreo y de color verde al resto de alumnos que sí pueden).

* Cuando los alumnos ya hayan salido a la calle, el profesor de guardia de patio acudirá a la zona del recreo para colaborar con el resto de compañeros en la guardia.

* Los alumnos pueden usar la Biblioteca durante los recreos. En este caso, una vez que hayan tomado el almuerzo en la entrada del centro, irán a la Biblioteca para permanecer en ella durante el resto del recreo.

* Pedimos colaboración a profesores que tienen clase a tercera hora para que se aseguren de que los alumnos cogen la ropa de abrigo y los almuerzos, apagan las luces y las pantallas y se cierra la puerta de la clase antes de ir al recreo.

* La puerta de entrada permanecerá cerrada desde las 11:30 hasta las 11:43.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-star">* La guardia se inicia con el primer timbre, es decir, a las 8:35 la de primera hora, a las 9:30 la de segunda y así sucesivamente cada una de las horas.</p>
<p class="cuaderno-perm-sub">o Al iniciarse la guardia con el primer timbre facilita que si algún compañero tiene que salir del aula antes del segundo timbre porque tenga clase en la hora siguiente, los alumnos no permanecen solos en el aula.</p>
<p class="cuaderno-perm-star">* La guardia de cuarta hora se inicia a las 11:45 para estar en los pasillos cuando los alumnos vayan subiendo del patio y entrando de la calle.</p>
<p class="cuaderno-perm-star">* Pedimos colaboración a los profesores que imparten clase en 1º y en 2º de ESO para que se queden en el aula con los alumnos hasta que llegue el profesor de la siguiente hora. o Si tienen clase en la hora siguiente, pueden esperar a que el profesor de guardia llegue para la guardia de cambio de hora para ir a su clase.</p>
<p class="cuaderno-perm-star">* Los periodos de guardia se realizarán por turnos entre los profesores de guardia en los pasillos y en la sala de profesores siempre y cuando no haya guardias de aula que cubrir por ausencias de profesores.</p>
<p class="cuaderno-perm-star">* Los profesores de guardia deben comprobar las ausencias de compañeros cuando lleguen al centro para organizar los turnos de guardia tanto en las clases como en los pasillos.</p>
<p class="cuaderno-perm-star">* Los profesores que cubran las guardias de aula no podrán rotar en la misma hora con otros compañeros; se podrá rotar semanalmente, si los profesores que realizan la guardia en la misma hora así lo deciden. Sí se podrá rotar el turno de guardia por el pasillo en la misma hora si los profesores así lo acuerdan.</p>
<p class="cuaderno-perm-star">* Se establecen turnos de guardia por el pasillo, uno por el de 1º y 3º de ESO y por los pasillos de CFGB y CFGM. Y otro turno por el pasillo de 2º y 4º de ESO.</p>
<p class="cuaderno-perm-star">* Para realizar las guardias de patio, se establece un turno rotatorio entre los profesores de tal manera que uno vigile los accesos al baño y los otros el respeto de las zonas asignadas a cada grupo en el patio.</p>
<p class="cuaderno-perm-sub">o Los profesores de patio controlarán además la organización de los turnos para que los alumnos vayan al baño (no más de dos alumnos a la vez).</p>
<p class="cuaderno-perm-star">* El profesor de pasillo se encargará de vigilar los pasillos y las aulas al inicio del recreo para evitar que el alumnado permanezca dentro de las clases y los alumnos que deben salir a la calle (a partir de 3º de ESO) permanezcan dentro del centro.</p>
<p class="cuaderno-perm-sub">o Además, se encargan de organizar el uso de baños por parte de los alumnos que suben del patio para poder ir.</p>
<p class="cuaderno-perm-star">* Uno de los profesores que se encuentre de guardia de pasillo se encargará de revisar si los alumnos que salen a la calle son los que tienen permiso para ello (se les ha entregado un carné de color rojo a los alumnos de 1º y 2º de ESO porque no pueden salir a la calle durante el recreo y de color verde al resto de alumnos que sí pueden).</p>
<p class="cuaderno-perm-star">* Cuando los alumnos ya hayan salido a la calle, el profesor de guardia de patio acudirá a la zona del recreo para colaborar con el resto de compañeros en la guardia.</p>
<p class="cuaderno-perm-star">* Los alumnos pueden usar la Biblioteca durante los recreos. En este caso, una vez que hayan tomado el almuerzo en la entrada del centro, irán a la Biblioteca para permanecer en ella durante el resto del recreo.</p>
<p class="cuaderno-perm-star">* Pedimos colaboración a profesores que tienen clase a tercera hora para que se aseguren de que los alumnos cogen la ropa de abrigo y los almuerzos, apagan las luces y las pantallas y se cierra la puerta de la clase antes de ir al recreo.</p>
<p class="cuaderno-perm-star">* La puerta de entrada permanecerá cerrada desde las 11:30 hasta las 11:43.</p>
</div>""",
    },
    {
        "id": "comunicaciones",
        "title": "4. Comunicaciones",
        "body": """Teams

* Las principales vías de comunicación son el TEAMS y la Plataforma de Comunicaciones.

* Cada profesor es miembro de los equipos comunes que corresponda (Claustro, Consejo Escolar, CCP, Tutores y Departamentos) y de los equipos docentes en los que imparte clase.

* Los tutores pueden solicitar información sobre los alumnos para transmitirla a la familia.

* Los profesores reseñarán los partes de incidencia que ponen a los alumnos del grupo a través del canal correspondiente del equipo docente.

Corcho sala de profesores

* Existen diferentes secciones donde se colocan distintas informaciones a lo largo del curso (cursos de formación, convivencia, sindicatos, otras informaciones).

* En este corcho se encuentran las llaves de las aulas de informática.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-subtitle">Teams</p>
<p class="cuaderno-perm-star">* Las principales vías de comunicación son el TEAMS y la Plataforma de Comunicaciones.</p>
<p class="cuaderno-perm-star">* Cada profesor es miembro de los equipos comunes que corresponda (Claustro, Consejo Escolar, CCP, Tutores y Departamentos) y de los equipos docentes en los que imparte clase.</p>
<p class="cuaderno-perm-star">* Los tutores pueden solicitar información sobre los alumnos para transmitirla a la familia.</p>
<p class="cuaderno-perm-star">* Los profesores reseñarán los partes de incidencia que ponen a los alumnos del grupo a través del canal correspondiente del equipo docente.</p>
<p class="cuaderno-perm-subtitle">Corcho sala de profesores</p>
<p class="cuaderno-perm-star">* Existen diferentes secciones donde se colocan distintas informaciones a lo largo del curso (cursos de formación, convivencia, sindicatos, otras informaciones).</p>
<p class="cuaderno-perm-star">* En este corcho se encuentran las llaves de las aulas de informática.</p>
</div>""",
    },
    {
        "id": "aulas-informatica",
        "title": "5. Aulas de informática y Biblioteca",
        "body": """* Los profesores pueden usar cuatro aulas de informática:
  o INFORMÁTICA A (206)
  o INFORMÁTICA B (210)
  o INFORMÁTICA C (209)
  o AULA MULTIMEDIA (301)

* Es obligatorio reservar el aula para hacer uso de las mismas.

* La reserva de las aulas se realiza a través de la aplicación de gestión del centro.

* Las llaves para acceder a las aulas se encuentran en el corcho de la Sala de Profesores.

* El profesor que vaya a usar el aula ha de coger la llave los cinco minutos antes de usarla y dejarla en cuanto termine la clase para que el siguiente profesor pueda acceder a la clase.

* Las instrucciones de uso de las aulas de informática se encuentran en la aplicación de reservas de aulas.

* Teniendo en cuenta las características de estas clases, os rogamos que os aseguréis del buen uso del material por parte de los alumnos.

* En las aulas de informática es obligatorio rellenar a través de la app «Aula de Informática» el puesto que ocupa cada alumno y el estado del equipo correspondiente.

* También se puede reservar en la aplicación la Biblioteca para su uso con alumnos durante alguna hora de clase. La llave de la Biblioteca se pide en Conserjería.

* Portátiles y Tablets: CUALQUIER MATERIAL DIGITAL DEL QUE SE QUIERA DISPONER SE SOLICITA EN SECRETARÍA:
  o Para pedir los portátiles o las tablets nos tenemos que apuntar en la hoja de registro de material en Secretaría.
  o Una vez usado dicho material, lo devolvemos para que pueda ser utilizado por otros compañeros.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-star">* Los profesores pueden usar cuatro aulas de informática:</p>
<p class="cuaderno-perm-sub">o INFORMÁTICA A (206)</p>
<p class="cuaderno-perm-sub">o INFORMÁTICA B (210)</p>
<p class="cuaderno-perm-sub">o INFORMÁTICA C (209)</p>
<p class="cuaderno-perm-sub">o AULA MULTIMEDIA (301)</p>
<p class="cuaderno-perm-star">* Es obligatorio reservar el aula para hacer uso de las mismas.</p>
<p class="cuaderno-perm-star">* La reserva de las aulas se realiza a través de la aplicación de gestión del centro.</p>
<p class="cuaderno-perm-star">* Las llaves para acceder a las aulas se encuentran en el corcho de la Sala de Profesores.</p>
<p class="cuaderno-perm-star">* El profesor que vaya a usar el aula ha de coger la llave los cinco minutos antes de usarla y dejarla en cuanto termine la clase para que el siguiente profesor pueda acceder a la clase.</p>
<p class="cuaderno-perm-star">* Las instrucciones de uso de las aulas de informática se encuentran en la aplicación de reservas de aulas.</p>
<p class="cuaderno-perm-star">* Teniendo en cuenta las características de estas clases, os rogamos que os aseguréis del buen uso del material por parte de los alumnos.</p>
<p class="cuaderno-perm-star">* En las aulas de informática es obligatorio rellenar a través de la app «Aula de Informática» el puesto que ocupa cada alumno y el estado del equipo correspondiente.</p>
<p class="cuaderno-perm-star">* También se puede reservar en la aplicación la Biblioteca para su uso con alumnos durante alguna hora de clase. La llave de la Biblioteca se pide en Conserjería.</p>
<p class="cuaderno-perm-star">* Portátiles y Tablets: CUALQUIER MATERIAL DIGITAL DEL QUE SE QUIERA DISPONER SE SOLICITA EN SECRETARÍA:</p>
<p class="cuaderno-perm-sub">o Para pedir los portátiles o las tablets nos tenemos que apuntar en la hoja de registro de material en Secretaría.</p>
<p class="cuaderno-perm-sub">o Una vez usado dicho material, lo devolvemos para que pueda ser utilizado por otros compañeros.</p>
</div>""",
    },
    {
        "id": "impresion-fotocopias",
        "title": "6. Impresión y fotocopias",
        "body": """Fotocopiadora de Conserjería

* Para sacar fotocopias hemos de pedirlo en Conserjería.

* Os pedimos un uso moderado de fotocopias.

* En la medida de lo posible se ruega hacer las fotocopias necesarias con la debida planificación y NO ENVIAR a alumnos a pedir copias.

* No se realizarán fotocopias antes de las 8:45, hasta esa hora los ordenanzas tienen la responsabilidad de velar por el correcto acceso de los alumnos y el personal al centro y abrir y cerrar puertas.

Fotocopiadora Sala de Profesores

* Esta fotocopiadora permite imprimir y fotocopiar documentos.

* Para acceder a su uso es necesario disponer de un código que se facilita desde secretaría.

Material de oficina

El material de oficina que tenemos en el centro (cartulinas, folios, cinta correctora, rotuladores…) es para uso de los profesores y para trabajos que tengan que ver con actividades del centro. El alumno traerá el material necesario para las actividades que les soliciten los profesores.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-subtitle">Fotocopiadora de Conserjería</p>
<p class="cuaderno-perm-star">* Para sacar fotocopias hemos de pedirlo en Conserjería.</p>
<p class="cuaderno-perm-star">* Os pedimos un uso moderado de fotocopias.</p>
<p class="cuaderno-perm-star">* En la medida de lo posible se ruega hacer las fotocopias necesarias con la debida planificación y NO ENVIAR a alumnos a pedir copias.</p>
<p class="cuaderno-perm-star">* No se realizarán fotocopias antes de las 8:45, hasta esa hora los ordenanzas tienen la responsabilidad de velar por el correcto acceso de los alumnos y el personal al centro y abrir y cerrar puertas.</p>
<p class="cuaderno-perm-subtitle">Fotocopiadora Sala de Profesores</p>
<p class="cuaderno-perm-star">* Esta fotocopiadora permite imprimir y fotocopiar documentos.</p>
<p class="cuaderno-perm-star">* Para acceder a su uso es necesario disponer de un código que se facilita desde secretaría.</p>
<p class="cuaderno-perm-subtitle">Material de oficina</p>
<p class="cuaderno-norma">El material de oficina que tenemos en el centro (cartulinas, folios, cinta correctora, rotuladores…) es para uso de los profesores y para trabajos que tengan que ver con actividades del centro. El alumno traerá el material necesario para las actividades que les soliciten los profesores.</p>
</div>""",
    },
    {
        "id": "normas-centro",
        "title": "7. Normas del centro",
        "body": """Estas normas las conocen los alumnos porque están colgadas en los de las aulas.

1) No está permitido el uso del móvil y otros aparatos electrónicos en horario lectivo (ni en los cambios de clase ni en las horas de guardia).

2) Los alumnos no pueden salir del aula en los cambios de clase. Cuando tengan que acudir a un aula específica, el profesor les recogerá en clase al inicio de la hora.

3) Los alumnos no esperan en el pasillo durante los cinco minutos de cambio para ir a otras aulas. Deben permanecer en el aula y esperar a que el profesor les vaya a buscar.

4) El baño se utiliza durante el recreo. Ante urgencia o necesidad imperiosa, excepcionalmente, se puede autorizar al alumno a ir al baño durante el tiempo de clase; nunca durante los cinco minutos de cambio. En ese caso se pedirá la llave del baño en la conserjería del pasillo de Jefatura.
o Los alumnos de 1º a 4º de ESO, grado básico y medio utilizan los baños que se encuentran en el pasillo de Jefatura de Estudios.
o Los alumnos de Bachillerato usan los baños del pasillo de Dirección. Cada uno de los grupos tiene una copia de las llaves para ir al baño sin necesidad de pedirlas en Conserjería. Estos alumnos deben hacer un uso adecuado de las llaves. En caso contrario, no se les darán las llaves.

5) Los justificantes de faltas se recogen en Jefatura de Estudios o Conserjería a las 8:35 y a las 14:30 (en el recreo los alumnos que a partir de 3º de ESO salen a la calle).

6) Recreo. Durante este tiempo los alumnos de 1º y 2º de ESO permanecen dentro del centro, en el patio como norma general. El resto de alumnos salen del centro. Los alumnos no pueden permanecer dentro de las aulas durante el recreo y por los pasillos del centro.

7) Si algún alumno se siente enfermo y necesita avisar a casa para que le recojan, tiene que ir a Jefatura a pedir que llamen (si desde Jefatura no se puede, pueden ir a Orientación o a Dirección).

8) Los alumnos no pueden salir del aula para ir a buscar material o fotocopias a Conserjería.

9) La hora de salida es a las 14:30. Los alumnos no pueden salir antes a no ser que la falta sea justificada.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-norma-intro">Estas normas las conocen los alumnos porque están colgadas en los de las aulas.</p>
<p class="cuaderno-norma">1) No está permitido el uso del móvil y otros aparatos electrónicos en horario lectivo (ni en los cambios de clase ni en las horas de guardia).</p>
<p class="cuaderno-norma">2) Los alumnos no pueden salir del aula en los cambios de clase. Cuando tengan que acudir a un aula específica, el profesor les recogerá en clase al inicio de la hora.</p>
<p class="cuaderno-norma">3) Los alumnos no esperan en el pasillo durante los cinco minutos de cambio para ir a otras aulas. Deben permanecer en el aula y esperar a que el profesor les vaya a buscar.</p>
<p class="cuaderno-norma">4) El baño se utiliza durante el recreo. Ante urgencia o necesidad imperiosa, excepcionalmente, se puede autorizar al alumno a ir al baño durante el tiempo de clase; nunca durante los cinco minutos de cambio. En ese caso se pedirá la llave del baño en la conserjería del pasillo de Jefatura.</p>
<p class="cuaderno-perm-sub">o Los alumnos de 1º a 4º de ESO, grado básico y medio utilizan los baños que se encuentran en el pasillo de Jefatura de Estudios.</p>
<p class="cuaderno-perm-sub">o Los alumnos de Bachillerato usan los baños del pasillo de Dirección. Cada uno de los grupos tiene una copia de las llaves para ir al baño sin necesidad de pedirlas en Conserjería. Estos alumnos deben hacer un uso adecuado de las llaves. En caso contrario, no se les darán las llaves.</p>
<p class="cuaderno-norma">5) Los justificantes de faltas se recogen en Jefatura de Estudios o Conserjería a las 8:35 y a las 14:30 (en el recreo los alumnos que a partir de 3º de ESO salen a la calle).</p>
<p class="cuaderno-norma">6) Recreo. Durante este tiempo los alumnos de 1º y 2º de ESO permanecen dentro del centro, en el patio como norma general. El resto de alumnos salen del centro. Los alumnos no pueden permanecer dentro de las aulas durante el recreo y por los pasillos del centro.</p>
<p class="cuaderno-norma">7) Si algún alumno se siente enfermo y necesita avisar a casa para que le recojan, tiene que ir a Jefatura a pedir que llamen (si desde Jefatura no se puede, pueden ir a Orientación o a Dirección).</p>
<p class="cuaderno-norma">8) Los alumnos no pueden salir del aula para ir a buscar material o fotocopias a Conserjería.</p>
<p class="cuaderno-norma">9) La hora de salida es a las 14:30. Los alumnos no pueden salir antes a no ser que la falta sea justificada.</p>
</div>""",
    },
    {
        "id": "partes-incidencias",
        "title": "8. Partes de incidencias",
        "body": """* Los partes de incidencias se dividen en leves y graves y muy graves, siguiendo el Reglamento de Régimen Interior del centro.

* Se comunican a Jefatura de Estudios a través de la aplicación de gestión del centro.

* El hecho de poner un parte de incidencias no supone que el alumno sea expulsado del aula; esto es una medida excepcional.

* Si un alumno es expulsado del aula debe ser enviado a la Sala de Visitas para que sea atendido por un profesor de guardia. La expulsión es considerada una falta grave, así constará en el parte de incidencias. El alumno expulsado debe llevar a la sala de Visitas un documento de comunicación que entregará al profesor de guardia donde conste el motivo de la expulsión, para que el profesor de guardia comunique telefónicamente a la familia dicha expulsión. Si el profesor que le ha puesto un parte a un alumno quiere comunicarlo a la familia, puede hacerlo a través de la aplicación de Comunicaciones de Stilus, o telefónicamente.

* El alumno expulsado debe llevar trabajo para realizar en el aula de expulsados.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-star">* Los partes de incidencias se dividen en leves y graves y muy graves, siguiendo el Reglamento de Régimen Interior del centro.</p>
<p class="cuaderno-perm-star">* Se comunican a Jefatura de Estudios a través de la aplicación de gestión del centro.</p>
<p class="cuaderno-perm-star">* El hecho de poner un parte de incidencias no supone que el alumno sea expulsado del aula; esto es una medida excepcional.</p>
<p class="cuaderno-perm-star">* Si un alumno es expulsado del aula debe ser enviado a la Sala de Visitas para que sea atendido por un profesor de guardia. La expulsión es considerada una falta grave, así constará en el parte de incidencias. El alumno expulsado debe llevar a la sala de Visitas un documento de comunicación que entregará al profesor de guardia donde conste el motivo de la expulsión, para que el profesor de guardia comunique telefónicamente a la familia dicha expulsión. Si el profesor que le ha puesto un parte a un alumno quiere comunicarlo a la familia, puede hacerlo a través de la aplicación de Comunicaciones de Stilus, o telefónicamente.</p>
<p class="cuaderno-perm-star">* El alumno expulsado debe llevar trabajo para realizar en el aula de expulsados.</p>
</div>""",
    },
    {
        "id": "tutores",
        "title": "9. Tutores",
        "body": """* Los tutores se encargan de la justificación de faltas de asistencia. Los alumnos pueden recoger justificantes de faltas en Conserjería o en Jefatura de Estudios a las 8:35 y a las 14:30 (en el recreo los pueden recoger los alumnos que salen a la calle).

* El plazo máximo para justificar una falta de asistencia es una semana después de la fecha de la falta.

* Deben rellenar y entregar un listado de llamadas (el modelo se encuentra en el grupo de Teams de Tutorías). En ese documento se señalan las llamadas realizadas durante dos semanas a las familias y el motivo por el que se ha comunicado con ellas.

* Los justificantes de faltas entregados por los alumnos y el listado de llamadas se entregan cada quince días (en las reuniones de tutores). El calendario de la celebración de las reuniones de tutores se encuentra en la Sala de Profesores, en la sección de Información general.

* El tutor debe comunicar a la familia el número de partes que tienen los alumnos (a partir de cinco).

* El tutor debe seleccionar a un alumno de la clase que sea el encargado de la llave. Este alumno recogerá la llave de la clase a primera hora en Conserjería y se encargará de cerrar el aula cada vez que se vayan a una específica y en el recreo.
  o Las aulas deben estar cerradas en el recreo y los alumnos no pueden permanecer dentro.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-star">* Los tutores se encargan de la justificación de faltas de asistencia. Los alumnos pueden recoger justificantes de faltas en Conserjería o en Jefatura de Estudios a las 8:35 y a las 14:30 (en el recreo los pueden recoger los alumnos que salen a la calle).</p>
<p class="cuaderno-perm-star">* El plazo máximo para justificar una falta de asistencia es una semana después de la fecha de la falta.</p>
<p class="cuaderno-perm-star">* Deben rellenar y entregar un listado de llamadas (el modelo se encuentra en el grupo de Teams de Tutorías). En ese documento se señalan las llamadas realizadas durante dos semanas a las familias y el motivo por el que se ha comunicado con ellas.</p>
<p class="cuaderno-perm-star">* Los justificantes de faltas entregados por los alumnos y el listado de llamadas se entregan cada quince días (en las reuniones de tutores). El calendario de la celebración de las reuniones de tutores se encuentra en la Sala de Profesores, en la sección de Información general.</p>
<p class="cuaderno-perm-star">* El tutor debe comunicar a la familia el número de partes que tienen los alumnos (a partir de cinco).</p>
<p class="cuaderno-perm-star">* El tutor debe seleccionar a un alumno de la clase que sea el encargado de la llave. Este alumno recogerá la llave de la clase a primera hora en Conserjería y se encargará de cerrar el aula cada vez que se vayan a una específica y en el recreo.</p>
<p class="cuaderno-perm-sub">o Las aulas deben estar cerradas en el recreo y los alumnos no pueden permanecer dentro.</p>
</div>""",
    },
    {
        "id": "aulas",
        "title": "10. Aulas",
        "body": """* Todas las aulas del centro deben estar cerradas con llave durante los períodos en los que no haya clase.

* Las aulas de referencia de grupo serán abiertas y cerradas por el alumno responsable que nombre el tutor.

* Debe tenerse en cuenta que las aulas de grupo pueden ser utilizadas por otros alumnos cuando los del grupo la abandonan para ir a otra materia, por lo que es muy importante no dejar material en la misma en esos períodos.

* Las aulas de desdoble serán abiertas y cerradas por los profesores que las vayan a utilizar, que deberán tener una copia de las llaves durante el curso que se les facilitará en Secretaría.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-star">* Todas las aulas del centro deben estar cerradas con llave durante los períodos en los que no haya clase.</p>
<p class="cuaderno-perm-star">* Las aulas de referencia de grupo serán abiertas y cerradas por el alumno responsable que nombre el tutor.</p>
<p class="cuaderno-perm-star">* Debe tenerse en cuenta que las aulas de grupo pueden ser utilizadas por otros alumnos cuando los del grupo la abandonan para ir a otra materia, por lo que es muy importante no dejar material en la misma en esos períodos.</p>
<p class="cuaderno-perm-star">* Las aulas de desdoble serán abiertas y cerradas por los profesores que las vayan a utilizar, que deberán tener una copia de las llaves durante el curso que se les facilitará en Secretaría.</p>
</div>""",
    },
    {
        "id": "actividades-extraescolares",
        "title": "11. Actividades complementarias y extraescolares",
        "body": """* Todas las actividades deben estar incluidas en la PGA o ser aprobadas explícitamente por el Consejo Escolar del Centro. Su planificación incluye la cumplimentación de la documentación y tras su realización debe adjuntarse una memoria al Departamento de Extraescolares.

* El promotor de cualquier actividad debe consignarla en la app de extraescolares, incluyendo fecha, horas de ausencia del Centro, profesores acompañantes y resto de detalles.

* Previo a la fecha de realización de la actividad el departamento organizador facilitará la lista de alumnos previstos a Jefatura de Estudios para revisión de las incidencias de comportamiento y de posibles alumnos sancionados.

* Ningún alumno podrá salir del Centro sin la autorización firmada por alguno de sus tutores legales. Es obligación del profesor que organice facilitar autorizaciones a los alumnos y recoger las mismas antes de la realización de la actividad.

* El plazo para que el alumno entregue la autorización firmada expira el día lectivo anterior al de la actividad.

* Existe un modelo tipo de autorización que se puede generar a través de la app de modo sencillo (Recomendable).

* Antes de la realización de la actividad debe ser confirmada por el promotor en la app para que conste como definitiva.

* Previo a la realización de la actividad debe entregarse en la administración del Centro el listado de alumnos para que el personal pueda consignarlo en las aplicaciones de la Junta.

* Existe un calendario en el portal para que cualquier profesor pueda consultar todas las actividades programadas, donde también se pueden consultar los alumnos asistentes.""",
        "body_html": """<div class="cuaderno-permisos">
<p class="cuaderno-perm-star">* Todas las actividades deben estar incluidas en la PGA o ser aprobadas explícitamente por el Consejo Escolar del Centro. Su planificación incluye la cumplimentación de la documentación y tras su realización debe adjuntarse una memoria al Departamento de Extraescolares.</p>
<p class="cuaderno-perm-star">* El promotor de cualquier actividad debe consignarla en la <a href="/extraescolares/dashboard">app de actividades extraescolares</a>, incluyendo fecha, horas de ausencia del Centro, profesores acompañantes y resto de detalles.</p>
<p class="cuaderno-perm-star">* Previo a la fecha de realización de la actividad el departamento organizador facilitará la lista de alumnos previstos a Jefatura de Estudios para revisión de las incidencias de comportamiento y de posibles alumnos sancionados.</p>
<p class="cuaderno-perm-star">* Ningún alumno podrá salir del Centro sin la autorización firmada por alguno de sus tutores legales. Es obligación del profesor que organice facilitar autorizaciones a los alumnos y recoger las mismas antes de la realización de la actividad.</p>
<p class="cuaderno-perm-star">* El plazo para que el alumno entregue la autorización firmada expira el día lectivo anterior al de la actividad.</p>
<p class="cuaderno-perm-star">* Existe un <a href="/extraescolares/autorizaciones">modelo tipo de autorización</a> que se puede generar a través de la app de modo sencillo (Recomendable).</p>
<p class="cuaderno-perm-star">* Antes de la realización de la actividad debe ser confirmada por el promotor en la app para que conste como definitiva.</p>
<p class="cuaderno-perm-star">* Previo a la realización de la actividad debe entregarse en la administración del Centro el listado de alumnos para que el personal pueda consignarlo en las aplicaciones de la Junta.</p>
<p class="cuaderno-perm-star">* Existe un <a href="/extraescolares/calendario">calendario en el portal</a> para que cualquier profesor pueda consultar todas las actividades programadas, donde también se pueden consultar los alumnos asistentes.</p>
</div>""",
    },
]
